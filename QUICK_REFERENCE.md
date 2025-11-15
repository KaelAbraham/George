# RQ Job Queue - Quick Reference

## What Makes This Commercial-Grade

- **Persistence:** Redis AOF/RDB protects queued work even if Redis crashes.
- **Observability:** `/monitoring/health`, `/monitoring/queue/stats`, `/monitoring/queue/workers`, and `/monitoring/queue/failed` expose health, queue depth, worker availability, and failed jobs.
- **Scalability:** Add or remove workers on demand with zero code changes.
- **Security:** Every worker-to-service call requires `INTERNAL_SERVICE_TOKEN` validation.
- **Recovery:** Automatic job recovery on startup re-queues interrupted work.
- **Monitoring:** The built-in RQ Dashboard offers real-time visibility into job states.

## Migration Path from the Legacy Workflow

1. **Install dependencies:** `pip install redis rq`.
2. **Start Redis locally:** `docker run -d -p 6379:6379 redis:7-alpine`.
3. **Update the backend:** Replace the old wiki endpoint in `backend/app.py` with the implementation from `artifact app_py_updates`.
4. **Adopt the new files:** copy `backend/job_manager.py`, `backend/tasks.py`, and `backend/worker.py` (overwrite existing `job_manager.py`).
5. **Clean up deprecated code:** remove `job_manager.run_async()` and `_run_wiki_generation_task()`.
6. **Smoke test:** start a worker, enqueue a job, and confirm it completes via the dashboard or `/jobs/{job_id}`.
7. **Deploy:** use `docker-compose` (see production section below) after validating locally.

### Breaking Changes

- Jobs must be created through `enqueue_job()` instead of `run_async()`.
- Task functions must be top-level, importable callables (no closures or nested defs).
- Workers now run as standalone processes (e.g., `python backend/worker.py --name worker-1`).

## Common Operations

### Start the System

```bash
# Development (3 terminals)
redis-server                                    # Terminal 1
python backend/app.py                           # Terminal 2
python backend/worker.py --name worker-1        # Terminal 3

# Production (Docker)
docker-compose up -d
```

### Check System Health

```bash
# Is everything running?
curl http://localhost:5000/monitoring/health

# Queue status
curl http://localhost:5000/monitoring/queue/stats

# Active workers
curl http://localhost:5000/monitoring/queue/workers
```

### Monitor Jobs

```bash
# Via RQ Dashboard (visual)
open http://localhost:9181

# Via API
curl http://localhost:5000/jobs/job_abc123
```

### Scale Workers

```bash
# Docker Compose
docker-compose up -d --scale worker-2=5

# Kubernetes
kubectl scale deployment caudex-worker --replicas=10

# Systemd
sudo systemctl start caudex-worker@{3..5}
```

### Troubleshooting

```bash
# Worker logs
docker-compose logs -f worker-1

# Failed jobs
curl http://localhost:5000/monitoring/queue/failed

# Retry a failed job
curl -X POST http://localhost:5000/monitoring/queue/failed \
  -H "Content-Type: application/json" \
  -d '{"rq_job_id": "abc-123"}'

# Restart everything
docker-compose restart
```

### Redis Operations

```bash
# Connect to Redis
redis-cli

# Check queue lengths
LLEN rq:queue:default
LLEN rq:queue:high

# View all keys
KEYS rq:*

# Flush all jobs (DANGER!)
FLUSHDB
```

## Code Patterns

### Create a New Task

```python
# backend/tasks.py
def my_new_task(project_id: str, user_id: str, param: str) -> Dict[str, Any]:
    """Task docstring."""
    from job_manager import JobManager
    job_manager = JobManager()
    
    rq_job = get_current_job()
    job_id = rq_job.id
    
    logger.info(f"[{job_id}] Starting task...")
    job_manager.update_job_progress(job_id, "PROCESSING")
    
    try:
        # Do work here
        result = {"status": "success", "data": param}
        
        job_manager.update_job_progress(job_id, "COMPLETED", result=result)
        return result
    except Exception as e:
        logger.error(f"[{job_id}] Task failed: {e}", exc_info=True)
        job_manager.update_job_progress(job_id, "FAILED", error=str(e))
        raise
```

### Enqueue a Job

```python
# backend/app.py
from tasks import my_new_task

@app.route('/start_task', methods=['POST'])
def start_task():
    job_id = job_manager.create_job(
        project_id=project_id,
        user_id=user_id,
        job_type="my_new_task"
    )
    
    job_manager.enqueue_job(
        job_id=job_id,
        task_func=my_new_task,
        project_id,    # positional args
        user_id,
        param="value",  # more positional args
        priority='default',  # or 'high'
        timeout=600     # 10 minutes
    )
    
    return jsonify({"job_id": job_id})
```

### Check Job Status

```json
# In your frontend
GET /jobs/{job_id}

# Response
{
  "job_id": "job_abc123",
  "status": "COMPLETED",  // PENDING, QUEUED, PROCESSING, COMPLETED, FAILED
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:32:15Z",
  "result": {
    "files_created": 5,
    "message": "Success!"
  }
}
```

## Environment Variables

### Required

```bash
REDIS_URL=redis://localhost:6379/0
INTERNAL_SERVICE_TOKEN=your-secret-here
```

### Optional

```bash
# Worker configuration
RQ_WORKER_NAME=worker-1
RQ_QUEUE_NAMES=high,default

# Redis persistence
REDIS_APPENDONLY=yes
REDIS_APPENDFSYNC=everysec

# Job retention
RQ_RESULT_TTL=86400      # 24 hours
RQ_FAILURE_TTL=604800    # 7 days
```

## File Locations

```
backend/
├── app.py              # Flask app (enqueues jobs)
├── job_manager.py      # Job lifecycle management
├── tasks.py            # Task definitions (executed by workers)
├── worker.py           # Worker process
└── data/
    └── jobs.db         # Job metadata (SQLite)

docker-compose.yml      # Production setup
DEPLOYMENT_GUIDE.md     # Full deployment docs
QUICK_REFERENCE.md      # This file
```

## Important URLs

- **Backend API**: http://localhost:5000
- **RQ Dashboard**: http://localhost:9181
- **Redis**: localhost:6379
- **Health Check**: http://localhost:5000/monitoring/health

## Key Differences from Old System

| Old (Threads) | New (RQ) |
|--------------|----------|
| Jobs lost on restart | Jobs survive restart |
| No retry capability | Automatic retry support |
| No monitoring | Web dashboard + API |
| Single worker (per server) | Multiple parallel workers |
| No queue priority | High/default queues |
| In-memory only | Redis persistence |

## Production Checklist

- [ ] Redis persistence enabled (AOF or RDB)
- [ ] At least 2 workers running
- [ ] INTERNAL_SERVICE_TOKEN set
- [ ] Redis AUTH enabled
- [ ] Worker logs configured
- [ ] Monitoring dashboard accessible
- [ ] Health check endpoint responding
- [ ] Backup strategy for Redis data
- [ ] Backup strategy for jobs.db
- [ ] Alert on worker failure

## Common Errors

### `redis.exceptions.ConnectionError`
**Fix:** Start Redis or check `REDIS_URL`

### `ModuleNotFoundError: No module named 'tasks'`
**Fix:** Worker needs Python path set:

```bash
PYTHONPATH=/app python backend/worker.py
```

### Jobs stuck in QUEUED
**Fix:** No workers running, start workers

### Jobs stuck in PROCESSING
**Fix:** Worker crashed, restart backend to trigger recovery

### High memory usage
**Fix:** Restart workers periodically:

```bash
python worker.py --max-jobs 1000
```
