import sqlite3
import uuid
import json
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any, Optional, Dict, List

# --- Job Status Constants ---
STATUS_QUEUED = "QUEUED"
STATUS_PROCESSING = "PROCESSING"
STATUS_WAITING_FOR_USER = "WAITING_FOR_USER"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"

logger = logging.getLogger(__name__)

class JobManager:
    """
    Manages all asynchronous, long-running tasks for the backend.
    This includes creating job records, running tasks in a background
    thread pool, and updating/retrieving job statuses.
    """
    
    def __init__(self, db_path: str = "data/jobs.db", max_workers: int = 3):
        """
        Initializes the JobManager.

        Args:
            db_path (str): Path to the SQLite database file for job tracking.
            max_workers (int): Max number of heavy tasks to run in parallel.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # This thread pool will run our heavy AI tasks in the background
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        self._init_db()
        logger.info(f"JobManager initialized. DB at {self.db_path}. Max workers: {max_workers}")

    def _get_conn(self) -> sqlite3.Connection:
        """Helper to get a new SQLite connection."""
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        """Creates the 'jobs' table if it doesn't already exist."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        job_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        completed_at DATETIME,
                        result TEXT,
                        error TEXT
                    )
                """)
                # Index for faster lookup of project history
                conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_project_user ON jobs (project_id, user_id)")
                conn.commit()
        except Exception as e:
            logger.critical(f"Failed to initialize JobManager database: {e}", exc_info=True)
            raise

    def create_job(self, project_id: str, user_id: str, job_type: str) -> str:
        """
        Creates a new job record in the database.
        This is the "receipt" for the user.

        Returns:
            str: The unique job_id.
        """
        job_id = str(uuid.uuid4())
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO jobs (job_id, project_id, user_id, job_type, status) VALUES (?, ?, ?, ?, ?)",
                    (job_id, project_id, user_id, job_type, STATUS_QUEUED)
                )
                conn.commit()
            logger.info(f"Created new job {job_id} ({job_type}) for user {user_id}.")
            return job_id
        except Exception as e:
            logger.error(f"Failed to create job: {e}", exc_info=True)
            raise

    def _update_job_status(self, job_id: str, status: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """Internal function to update a job's status, result, or error."""
        try:
            with self._get_conn() as conn:
                if status in [STATUS_COMPLETED, STATUS_FAILED]:
                    completed_time = datetime.utcnow()
                    conn.execute(
                        """UPDATE jobs SET status = ?, result = ?, error = ?, completed_at = ? 
                           WHERE job_id = ?""",
                        (status, json.dumps(result) if result else None, error, completed_time, job_id)
                    )
                elif status == STATUS_WAITING_FOR_USER and result:
                     # Special case: Update result (preview data) but don't set completed_at
                     conn.execute(
                        "UPDATE jobs SET status = ?, result = ? WHERE job_id = ?",
                        (status, json.dumps(result), job_id)
                    )
                else:
                    conn.execute("UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update job {job_id} status to {status}: {e}")

    def run_async(self, job_id: str, task_function: Callable[..., Any], *args: Any, **kwargs: Any):
        """
        Submits the actual heavy task to the background thread pool.
        This function returns immediately.
        """
        
        def _task_wrapper():
            """This wrapper function is what the thread actually runs."""
            logger.info(f"Starting background processing for job {job_id}...")
            self._update_job_status(job_id, STATUS_PROCESSING)
            
            try:
                # Run the actual heavy-lifting function
                # e.g., _run_wiki_generation_task(project_id)
                result = task_function(*args, **kwargs)
                
                # Note: If the task function explicitly returned a special status 
                # (like forcing a pause), we could handle it here. 
                # For now, we assume successful return = COMPLETED.
                
                # Success!
                self._update_job_status(job_id, STATUS_COMPLETED, result=result)
                logger.info(f"Job {job_id} completed successfully.")
                
            except Exception as e:
                # Failure!
                logger.error(f"Job {job_id} failed: {e}", exc_info=True)
                self._update_job_status(job_id, STATUS_FAILED, error=str(e))

        # Submit the wrapper to the pool. This returns immediately.
        self.executor.submit(_task_wrapper)

    def pause_job_for_user(self, job_id: str, preview_data: Dict[str, Any]):
        """
        Special function for multi-step jobs like Web Import.
        Sets the job to WAITING_FOR_USER and stores the preview data.
        """
        logger.info(f"Pausing job {job_id} for user confirmation.")
        self._update_job_status(job_id, STATUS_WAITING_FOR_USER, result=preview_data)

    def resume_job(self, job_id: str, task_function: Callable[..., Any], *args: Any, **kwargs: Any):
        """
        Resumes a job that was waiting for user input.
        Effectively just runs a new async task under the existing job ID.
        """
        logger.info(f"Resuming job {job_id}...")
        self.run_async(job_id, task_function, *args, **kwargs)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single job's status and details."""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
                row = cursor.fetchone()
                if row:
                    result_dict = dict(row)
                    # Parse JSON result back to dict if it exists
                    if result_dict.get('result'):
                        try:
                            result_dict['result'] = json.loads(result_dict['result'])
                        except json.JSONDecodeError:
                            pass 
                    return result_dict
                return None
        except Exception as e:
            logger.error(f"Failed to get job {job_id}: {e}")
            return None

    def get_jobs_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        """Lists all jobs (newest first) for a given project."""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC", 
                    (project_id,)
                )
                jobs = []
                for row in cursor.fetchall():
                    job = dict(row)
                    if job.get('result'):
                        try:
                            job['result'] = json.loads(job['result'])
                        except: 
                            pass
                    jobs.append(job)
                return jobs
        except Exception as e:
            logger.error(f"Failed to get jobs for project {project_id}: {e}")
            return []