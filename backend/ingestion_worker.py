#!/usr/bin/env python3
"""
Ingestion Worker: Background Process for Async Chat History Ingestion

This script runs as a separate process and continuously monitors the ingestion_queue
table in sessions.db. It pulls pending messages and performs the full File -> Vector -> Graph
orchestration asynchronously, decoupling the chat experience from knowledge base updates.

The worker:
1. Polls ingestion_queue for pending messages
2. Fetches chat turn data using session_manager
3. Formats as Markdown
4. Saves to filesystem_server
5. Indexes in chroma_server
6. Commits to git_server
7. Marks queue record as complete

This keeps chat fast while ensuring Story Bible is eventually consistent.
"""

import os
import sys
import time
import logging
import requests
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from session_manager import SessionManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('logs/ingestion_worker.log', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('IngestionWorker')

# Microservice URLs
# Internal service URLs (6000-series ports are reserved for internal services)
FILESYSTEM_SERVER_URL = os.getenv('FILESYSTEM_SERVER_URL', 'http://localhost:6002')
CHROMA_SERVER_URL = os.getenv('CHROMA_SERVER_URL', 'http://localhost:6003')
GIT_SERVER_URL = os.getenv('GIT_SERVER_URL', 'http://localhost:6005')

# Worker configuration
POLL_INTERVAL = 5  # Check queue every 5 seconds
BATCH_SIZE = 10    # Process up to 10 messages per cycle
RETRY_LIMIT = 3    # Retry failed ingestions up to 3 times

class IngestionWorker:
    """Background worker for ingesting chat messages into the knowledge base."""
    
    def __init__(self, db_path: str = "data/sessions.db"):
        """Initialize the worker."""
        self.db_path = db_path
        self.session_manager = SessionManager(db_path)
        self.logger = logger
        self.logger.info("✓ IngestionWorker initialized")
    
    def process_queue(self) -> int:
        """
        Process pending ingestions from the queue.
        
        Returns:
            int: Number of messages successfully ingested
        """
        try:
            # Get pending messages
            pending = self.session_manager.get_pending_ingestions(limit=BATCH_SIZE)
            
            if not pending:
                return 0
            
            self.logger.info(f"Processing {len(pending)} pending ingestions...")
            
            success_count = 0
            for queue_record in pending:
                if self._ingest_message(queue_record):
                    success_count += 1
            
            self.logger.info(f"Processed {success_count}/{len(pending)} ingestions successfully")
            return success_count
        
        except Exception as e:
            self.logger.error(f"Error processing queue: {e}", exc_info=True)
            return 0
    
    def _ingest_message(self, queue_record: dict) -> bool:
        """
        Perform the complete ingestion workflow for a single message.
        
        Steps:
        1. Fetch turn data
        2. Format as Markdown
        3. Save to filesystem
        4. Index in Chroma
        5. Commit to Git
        
        Args:
            queue_record (dict): Queue record with message_id, project_id, user_id, id
            
        Returns:
            bool: True if ingestion succeeded, False otherwise
        """
        message_id = queue_record['message_id']
        project_id = queue_record['project_id']
        user_id = queue_record['user_id']
        queue_id = queue_record['id']
        
        try:
            self.logger.info(f"Ingesting message {message_id}...")
            
            # Step 1: Fetch turn data
            turn_data = self.session_manager.get_turn_by_id(message_id, user_id)
            if not turn_data:
                error_msg = f"Could not retrieve turn data for message {message_id}"
                self.logger.error(error_msg)
                self.session_manager.mark_ingestion_complete(queue_id, 'failed', error_msg)
                return False
            
            # Step 2: Format as Markdown
            note_content = f"""# Chat Note: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## User Query
{turn_data['user_query']}

## George's Response
{turn_data['ai_response']}
"""
            note_filename = f"notes/note_{message_id}.md"
            
            # Step 3: Save to filesystem
            file_saved = self._save_to_filesystem(project_id, user_id, note_filename, note_content)
            
            # Step 4: Index in Chroma (even if filesystem failed - graceful degradation)
            vector_indexed = self._index_to_chroma(project_id, message_id, note_filename, note_content, user_id)
            
            # Step 5: Commit to Git (even if earlier steps failed)
            git_committed = self._commit_to_git(project_id, user_id, message_id, note_filename, turn_data)
            
            # Determine overall success
            overall_success = file_saved or vector_indexed or git_committed
            
            if overall_success:
                self.logger.info(
                    f"✓ Ingestion complete for {message_id}: "
                    f"file={file_saved}, vector={vector_indexed}, git={git_committed}"
                )
                self.session_manager.mark_ingestion_complete(queue_id, 'complete')
                return True
            else:
                error_msg = "All ingestion steps failed"
                self.logger.error(f"✗ {error_msg} for message {message_id}")
                self.session_manager.mark_ingestion_complete(queue_id, 'failed', error_msg)
                return False
        
        except Exception as e:
            self.logger.error(f"Unexpected error ingesting message {message_id}: {e}", exc_info=True)
            self.session_manager.mark_ingestion_complete(queue_id, 'failed', str(e))
            return False
    
    def _save_to_filesystem(self, project_id: str, user_id: str, note_filename: str, content: str) -> bool:
        """
        Save note to filesystem_server.
        
        Returns:
            bool: True if successful
        """
        try:
            payload = {
                "project_id": project_id,
                "file_path": note_filename,
                "content": content
            }
            response = requests.post(
                f"{FILESYSTEM_SERVER_URL}/save_file",
                json=payload,
                headers={'X-User-ID': user_id},
                timeout=10
            )
            response.raise_for_status()
            self.logger.debug(f"✓ Saved to filesystem: {note_filename}")
            return True
        except Exception as e:
            self.logger.warning(f"✗ Filesystem save failed for {note_filename}: {e}")
            return False
    
    def _index_to_chroma(self, project_id: str, message_id: str, note_filename: str, content: str, user_id: str) -> bool:
        """
        Index note in Chroma vector database.
        
        Returns:
            bool: True if successful
        """
        try:
            payload = {
                "collection_name": f"project_{project_id}",
                "documents": [content],
                "metadatas": [{
                    "source_file": note_filename,
                    "type": "auto_ingested_chat",
                    "created_by": user_id
                }],
                "ids": [message_id]
            }
            response = requests.post(
                f"{CHROMA_SERVER_URL}/add",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            self.logger.debug(f"✓ Indexed in Chroma: {message_id}")
            return True
        except Exception as e:
            self.logger.warning(f"✗ Chroma indexing failed for {message_id}: {e}")
            return False
    
    def _commit_to_git(self, project_id: str, user_id: str, message_id: str, note_filename: str, turn_data: dict) -> bool:
        """
        Commit note to git_server.
        
        Returns:
            bool: True if successful
        """
        try:
            payload = {
                "project_id": project_id,
                "user_id": user_id,
                "message": f"Auto-ingest chat: {note_filename}",
                "description": f"Auto-ingested from chat session.\n\nPrompt: {turn_data['user_query'][:100]}...\n\nMessage ID: {message_id}"
            }
            response = requests.post(
                f"{GIT_SERVER_URL}/snapshot",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            self.logger.debug(f"✓ Committed to Git: {message_id}")
            return True
        except Exception as e:
            self.logger.warning(f"✗ Git commit failed for {message_id}: {e}")
            return False
    
    def run(self):
        """
        Main worker loop. Continuously polls and processes the ingestion queue.
        This should run as a separate process or daemon.
        """
        self.logger.info("=" * 60)
        self.logger.info("INGESTION WORKER STARTED")
        self.logger.info("=" * 60)
        self.logger.info(f"Filesystem Server: {FILESYSTEM_SERVER_URL}")
        self.logger.info(f"Chroma Server: {CHROMA_SERVER_URL}")
        self.logger.info(f"Git Server: {GIT_SERVER_URL}")
        self.logger.info(f"Poll Interval: {POLL_INTERVAL}s")
        self.logger.info(f"Batch Size: {BATCH_SIZE}")
        self.logger.info("=" * 60)
        
        cycle = 0
        last_activity = datetime.now()
        
        try:
            while True:
                cycle += 1
                processed = self.process_queue()
                
                if processed > 0:
                    last_activity = datetime.now()
                
                # Log activity every 30 cycles
                if cycle % 30 == 0:
                    idle_time = (datetime.now() - last_activity).total_seconds()
                    self.logger.info(
                        f"[Cycle {cycle}] Idle for {idle_time:.0f}s. "
                        f"Processed {processed} messages. "
                        f"Waiting for ingestions..."
                    )
                
                time.sleep(POLL_INTERVAL)
        
        except KeyboardInterrupt:
            self.logger.info("\n" + "=" * 60)
            self.logger.info("INGESTION WORKER SHUTTING DOWN")
            self.logger.info("=" * 60)
        except Exception as e:
            self.logger.critical(f"FATAL ERROR: {e}", exc_info=True)
            sys.exit(1)


def main():
    """Entry point for the ingestion worker."""
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)
    
    # Create and run worker
    worker = IngestionWorker(db_path="data/sessions.db")
    worker.run()


if __name__ == '__main__':
    main()
