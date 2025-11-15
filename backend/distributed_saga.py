"""
Distributed Transaction Support with Saga Pattern
Handles transactional consistency across microservices.
"""
import logging
import requests
from typing import Callable, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SagaState(Enum):
    """States of a saga transaction."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class SagaStep:
    """Represents a single step in a saga with its rollback action."""
    name: str
    action: Callable[[], Any]
    rollback: Callable[[], None]
    executed: bool = False
    result: Any = None
    error: Exception = None


class DistributedSaga:
    """
    Implements the Saga Pattern for distributed transactions.
    
    The Saga Pattern coordinates multiple service calls with rollback capabilities:
    - If a step fails, all previous steps are rolled back in reverse order
    - Each step has an associated rollback action
    - Provides transactional semantics across microservices
    
    Usage:
        saga = DistributedSaga("wiki-generation", user_id=user_id)
        try:
            files = saga.execute_step(
                name="Save wiki files",
                action=lambda: save_files_to_filesystem(files),
                rollback=lambda: delete_files_from_filesystem(file_paths)
            )
            snapshot = saga.execute_step(
                name="Create git snapshot",
                action=lambda: create_git_snapshot(project_id),
                rollback=lambda: delete_git_snapshot(snapshot_id)
            )
            saga.commit()
        except Exception as e:
            logger.error(f"Saga failed: {e}, rolling back all changes")
            # Rollback is automatic on exception
            raise
    """
    
    def __init__(self, saga_id: str, user_id: str = None):
        """
        Initialize a saga transaction.
        
        Args:
            saga_id: Unique identifier for this saga (for logging)
            user_id: User ID associated with this saga (for audit)
        """
        self.saga_id = saga_id
        self.user_id = user_id
        self.state = SagaState.PENDING
        self.steps: List[SagaStep] = []
        self.committed_steps: List[SagaStep] = []
        self.failed_at_step: SagaStep = None
        
    def execute_step(
        self, 
        name: str, 
        action: Callable[[], Any], 
        rollback: Callable[[], None]
    ) -> Any:
        """
        Execute a step in the saga with automatic rollback on failure.
        
        Args:
            name: Human-readable name of the step
            action: Function to execute
            rollback: Function to call if transaction fails
            
        Returns:
            Result from the action function
            
        Raises:
            Exception: If the action fails (triggers rollback)
        """
        if self.state != SagaState.PENDING and self.state != SagaState.EXECUTING:
            raise RuntimeError(f"Cannot execute step: saga state is {self.state.value}")
        
        self.state = SagaState.EXECUTING
        step = SagaStep(name=name, action=action, rollback=rollback)
        self.steps.append(step)
        
        try:
            logger.info(f"[{self.saga_id}] Executing step: {name}")
            result = action()
            step.executed = True
            step.result = result
            self.committed_steps.append(step)
            logger.info(f"[{self.saga_id}] ✓ Step completed: {name}")
            return result
            
        except Exception as e:
            logger.error(f"[{self.saga_id}] ✗ Step failed: {name} - {e}")
            self.state = SagaState.FAILED
            self.failed_at_step = step
            step.error = e
            self._rollback_all()
            raise
    
    def commit(self) -> None:
        """
        Mark the saga as committed (all steps successful).
        No actual rollback actions are taken at this point.
        """
        if self.state == SagaState.EXECUTING:
            self.state = SagaState.COMMITTED
            logger.info(f"[{self.saga_id}] ✓ Saga committed successfully with {len(self.committed_steps)} steps")
        else:
            raise RuntimeError(f"Cannot commit saga in state {self.state.value}")
    
    def _rollback_all(self) -> None:
        """
        Rollback all committed steps in reverse order.
        Called automatically on step failure.
        """
        if self.state == SagaState.ROLLED_BACK:
            logger.warning(f"[{self.saga_id}] Rollback already in progress")
            return
        
        self.state = SagaState.ROLLED_BACK
        logger.warning(f"[{self.saga_id}] Rolling back {len(self.committed_steps)} completed steps")
        
        # Rollback in reverse order
        for step in reversed(self.committed_steps):
            try:
                logger.info(f"[{self.saga_id}] Rolling back: {step.name}")
                step.rollback()
                logger.info(f"[{self.saga_id}] ✓ Rollback successful: {step.name}")
            except Exception as e:
                logger.error(f"[{self.saga_id}] ✗ Rollback failed for {step.name}: {e}")
                # Continue rolling back other steps even if one fails
    
    def get_status(self) -> dict:
        """Get the current status of the saga."""
        return {
            "saga_id": self.saga_id,
            "user_id": self.user_id,
            "state": self.state.value,
            "total_steps": len(self.steps),
            "completed_steps": len(self.committed_steps),
            "failed_at": self.failed_at_step.name if self.failed_at_step else None,
            "error": str(self.failed_at_step.error) if self.failed_at_step and self.failed_at_step.error else None
        }


class WikiGenerationSaga(DistributedSaga):
    """
    Specialized saga for wiki generation with proper rollback.
    
    Steps:
    1. Save files to filesystem (rollback: delete files)
    2. Create git snapshot (rollback: delete snapshot)
    
    If any step fails, all previous changes are rolled back.
    """
    
    def __init__(self, project_id: str, user_id: str, 
                 filesystem_url: str, git_url: str, internal_headers: dict):
        """
        Initialize wiki generation saga.
        
        Args:
            project_id: Project ID
            user_id: User ID
            filesystem_url: Filesystem server URL
            git_url: Git server URL
            internal_headers: Headers for inter-service authentication
        """
        super().__init__(saga_id=f"wiki-{project_id}", user_id=user_id)
        self.project_id = project_id
        self.filesystem_url = filesystem_url
        self.git_url = git_url
        self.internal_headers = internal_headers
        self.saved_files = []  # Track saved file paths for rollback
        self.snapshot_id = None  # Track snapshot ID for rollback
    
    def save_wiki_files(self, files: List[dict]) -> Tuple[List[str], int]:
        """
        Save wiki files with rollback capability.
        
        Args:
            files: List of file dicts with 'filename' and 'content'
            
        Returns:
            Tuple of (file_paths, saved_count)
        """
        saved_file_paths = []
        saved_count = 0
        
        def save_action():
            """Execute: Save all files to filesystem."""
            for file_data in files:
                filename = file_data.get('filename', 'unknown.md')
                content = file_data.get('content', '')
                file_path = f"wiki/{filename}"
                
                save_payload = {
                    "project_id": self.project_id,
                    "file_path": file_path,
                    "content": content
                }
                
                resp = requests.post(
                    f"{self.filesystem_url}/save_file",
                    json=save_payload,
                    headers={**{'X-User-ID': self.user_id}, **self.internal_headers},
                    timeout=10
                )
                resp.raise_for_status()
                
                saved_file_paths.append(file_path)
                logger.debug(f"Saved file: {file_path}")
            
            return (saved_file_paths, len(saved_file_paths))
        
        def rollback_action():
            """Rollback: Delete all saved files."""
            if not saved_file_paths:
                return
            
            logger.warning(f"Rolling back {len(saved_file_paths)} saved files")
            for file_path in saved_file_paths:
                try:
                    resp = requests.delete(
                        f"{self.filesystem_url}/file/{self.project_id}/{file_path.replace('wiki/', '')}",
                        headers={**{'X-User-ID': self.user_id}, **self.internal_headers},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        logger.info(f"Deleted file: {file_path}")
                    else:
                        logger.warning(f"Failed to delete file {file_path}: {resp.status_code}")
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {e}")
        
        return self.execute_step(
            name=f"Save {len(files)} wiki files to filesystem",
            action=save_action,
            rollback=rollback_action
        )
    
    def create_git_snapshot(self, num_files: int, num_relationships: int) -> str:
        """
        Create git snapshot with rollback capability.
        
        Args:
            num_files: Number of files saved
            num_relationships: Number of relationships extracted
            
        Returns:
            Snapshot ID
        """
        snapshot_id_holder = {}  # To capture snapshot_id in closure
        
        def snapshot_action():
            """Execute: Create git snapshot."""
            git_resp = requests.post(
                f"{self.git_url}/snapshot/{self.project_id}",
                json={
                    "user_id": self.user_id,
                    "message": f"Auto-generated wiki with {num_files} files and {num_relationships} relationships."
                },
                timeout=15,
                headers=self.internal_headers
            )
            git_resp.raise_for_status()
            
            snapshot_id = git_resp.json().get('snapshot_id')
            snapshot_id_holder['id'] = snapshot_id
            logger.info(f"Created git snapshot: {snapshot_id}")
            return snapshot_id
        
        def snapshot_rollback():
            """Rollback: Delete git snapshot."""
            if 'id' not in snapshot_id_holder:
                return
            
            snapshot_id = snapshot_id_holder['id']
            logger.warning(f"Rolling back git snapshot: {snapshot_id}")
            
            try:
                resp = requests.delete(
                    f"{self.git_url}/snapshot/{self.project_id}/{snapshot_id}",
                    timeout=15,
                    headers=self.internal_headers
                )
                if resp.status_code == 200:
                    logger.info(f"Deleted git snapshot: {snapshot_id}")
                else:
                    logger.warning(f"Failed to delete git snapshot: {resp.status_code}")
            except Exception as e:
                logger.error(f"Error deleting git snapshot: {e}")
        
        return self.execute_step(
            name="Create git snapshot of wiki files",
            action=snapshot_action,
            rollback=snapshot_rollback
        )
    
    def execute_with_consistency(self, files: List[dict]) -> dict:
        """
        Execute full wiki generation saga with transactional consistency.
        
        If any step fails, all previous steps are automatically rolled back.
        
        Args:
            files: List of generated wiki files
            
        Returns:
            Result dict with files created, snapshot ID, etc.
        """
        try:
            # Step 1: Save files
            file_paths, saved_count = self.save_wiki_files(files)
            
            # Step 2: Create git snapshot
            snapshot_id = self.create_git_snapshot(
                num_files=saved_count,
                num_relationships=0  # Would be passed in real implementation
            )
            
            # All steps succeeded
            self.commit()
            
            return {
                "status": "success",
                "files_created": saved_count,
                "snapshot_id": snapshot_id,
                "file_paths": file_paths,
                "message": f"Wiki generated with {saved_count} files and snapshot {snapshot_id}"
            }
            
        except Exception as e:
            logger.error(f"Wiki generation saga failed: {e}", exc_info=True)
            # Rollback happens automatically on exception in execute_step
            return {
                "status": "failed",
                "error": "Wiki generation failed",
                "saga_status": self.get_status()
            }
