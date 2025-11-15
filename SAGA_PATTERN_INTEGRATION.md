# Saga Pattern Integration Guide

## Overview

The Saga Pattern has been successfully integrated into the wiki generation workflow to ensure **transactional consistency** across microservices. This document explains the implementation, benefits, and usage.

**Commit:** `0049ddc` - feat: Integrate WikiGenerationSaga into wiki generation workflow

---

## Problem Solved

### Previous Behavior (Vulnerable)
```
Step 1-4: Fetch docs, generate files, extract relationships, save to graph
   ✓ Success
Step 5: Save files to filesystem_server
   ✓ Success (files now exist)
Step 6: Create git snapshot
   ✗ FAILURE! (service down, timeout, etc.)
   
RESULT: Orphaned files exist in filesystem but no snapshot/audit trail
        Data inconsistency between services
```

### New Behavior (Safe)
```
Step 1-4: Fetch docs, generate files, extract relationships, save to graph
   ✓ Success

Saga Transaction Begins (All-or-Nothing):
   Step 5: Save files to filesystem_server
      ✓ Success (tracked for rollback)
   Step 6: Create git snapshot
      ✗ FAILURE! (service down, timeout, etc.)
      
   Automatic Rollback (Reverse Order):
      Step 5 Rollback: Delete all saved files
         ✓ Success
      
RESULT: No orphaned files, no partial transactions
        Data consistency guaranteed across services
```

---

## Architecture

### Saga Pattern Components

#### 1. `DistributedSaga` Base Class
```python
from distributed_saga import DistributedSaga

saga = DistributedSaga(saga_id="operation-123", user_id="user-456")

# Define a step with action and rollback
result = saga.execute_step(
    name="Step description",
    action=lambda: perform_operation(),      # What to do
    rollback=lambda: undo_operation()        # How to undo
)

# Mark saga as complete
saga.commit()
```

**Features:**
- Tracks all steps and their results
- Automatic rollback on any failure
- Rolls back in **reverse order** (LIFO)
- Maintains saga state (PENDING → EXECUTING → COMMITTED/FAILED)
- Comprehensive logging with saga_id prefix

**States:**
- `PENDING`: Initial state
- `EXECUTING`: Currently executing a step
- `COMMITTED`: All steps successful
- `ROLLED_BACK`: Rolled back after failure
- `FAILED`: Failed and couldn't rollback completely

#### 2. `WikiGenerationSaga` Specialized Class
```python
from distributed_saga import WikiGenerationSaga

saga = WikiGenerationSaga(
    project_id="proj-123",
    user_id="user-456",
    filesystem_url="http://localhost:6001",
    git_url="http://localhost:6003",
    internal_headers={"X-INTERNAL-TOKEN": "token123"}
)

# Execute two coordinated operations
result = saga.execute_with_consistency(generated_files)
```

**Built-in Steps:**
1. `save_wiki_files()` - Saves files to filesystem_server with delete rollback
2. `create_git_snapshot()` - Creates git snapshot with delete rollback

#### 3. Saga State Tracking
```python
# Get saga status at any point
status = saga.get_status()
print(status)
# {
#     "saga_id": "wiki-proj-123",
#     "user_id": "user-456",
#     "state": "committed",
#     "total_steps": 2,
#     "completed_steps": 2,
#     "failed_at": None,
#     "error": None
# }
```

---

## Integration with Wiki Generation

### File Structure
```
backend/
├── app.py                      # Main service (updated)
├── distributed_saga.py         # Saga pattern implementation (NEW)
├── service_utils.py            # Shared utilities
└── [other services]
```

### Updated Function Signature

**Function:** `_run_wiki_generation_task(project_id, user_id) → Dict`

**Steps 1-4:** Traditional execution (before saga)
- Step 1: Get documents from chroma_server
- Step 2: Generate wiki files via orchestrator
- Step 3: Extract relationships from documents
- Step 4: Save relationships to Neo4j graph

**Steps 5-6:** Saga transaction (NEW)
- Step 5: Save files to filesystem_server (tracked for rollback)
- Step 6: Create git snapshot (tracked for rollback)

### Code Flow

```python
from distributed_saga import WikiGenerationSaga
from service_utils import get_internal_headers

def _run_wiki_generation_task(project_id: str, user_id: str) -> Dict:
    # ... Steps 1-4 (traditional, no saga) ...
    
    # Step 5-6: Use saga for transactional consistency
    saga = WikiGenerationSaga(
        project_id=project_id,
        user_id=user_id,
        filesystem_url=FILESYSTEM_SERVER_URL,
        git_url=GIT_SERVER_URL,
        internal_headers=get_internal_headers()
    )
    
    try:
        result = saga.execute_with_consistency(generated_files)
        
        if result["status"] == "success":
            return {
                "files_created": result["files_created"],
                "snapshot_id": result["snapshot_id"],
                "relationships_extracted": len(relationships),
                "message": result["message"]
            }
        else:
            # Saga failed and was rolled back
            raise Exception(f"Wiki generation saga failed: {result['error']}")
            
    except Exception as e:
        # Saga already rolled back automatically
        raise Exception(f"Wiki generation failed and was rolled back: {e}")
```

### Execution Sequence Diagram

```
Client Request to /generate_wiki
    ↓
_run_wiki_generation_task()
    ├─ Step 1: Fetch from chroma_server ✓
    │   └─ Get all documents
    │
    ├─ Step 2: Call orchestrator ✓
    │   └─ Generate markdown files
    │
    ├─ Step 3: Extract relationships ✓
    │   └─ Find entity connections
    │
    ├─ Step 4: Save to Neo4j ✓
    │   └─ Store relationship triples
    │
    └─ Saga Transaction (All-or-Nothing)
        ├─ Step 5: Save files
        │   │   POST /save_file → filesystem_server
        │   │   [Track file IDs for rollback]
        │   │   ✓ Success
        │   │
        │   ├─ Step 6: Create snapshot
        │   │   POST /snapshot/{project_id} → git_server
        │   │   [Track snapshot_id for rollback]
        │   │   ✗ FAILURE (service down, timeout, etc.)
        │   │
        │   └─ Automatic Rollback (Reverse Order)
        │       └─ Delete files from filesystem_server
        │           [Using tracked file IDs]
        │           ✓ Rollback success
        │
        └─ Return failure (no orphaned state)

Response: { "status": "failure", "error": "...", "saga_status": {...} }
```

---

## Logging

### Saga Logging Format

Every saga operation logs with the pattern: `[{saga_id}] {action}`

**Examples:**
```
[wiki-proj-123] Executing step: Save 45 wiki files to filesystem
[wiki-proj-123] ✓ Step completed: Save 45 wiki files to filesystem
[wiki-proj-123] ✗ Step failed: Create git snapshot of wiki files - Connection refused
[wiki-proj-123] Rolling back 1 completed steps
[wiki-proj-123] Rolling back: Save 45 wiki files to filesystem
[wiki-proj-123] ✓ Rollback successful: Save 45 wiki files to filesystem
[wiki-proj-123] ✓ Saga committed successfully with 2 steps
```

### Log Levels

- **INFO**: Normal operation, step execution, success, commit
- **ERROR**: Step failures, rollback failures
- **WARNING**: Rollback execution, partial failures during rollback

---

## Error Handling

### Automatic Error Recovery

**Scenario 1: Service Timeout**
```python
# If git_server times out during snapshot creation:
try:
    saga.execute_with_consistency(files)
except RequestException:
    # Automatically rolls back saved files
    # Returns: { "status": "failed", "error": "...", "saga_status": {...} }
```

**Scenario 2: Service Returned Error**
```python
# If filesystem_server returns 500 during save:
try:
    saga.execute_with_consistency(files)
except Exception:
    # No files were saved, nothing to rollback
    # Returns failure immediately
```

**Scenario 3: Partial Rollback Failure**
```python
# If rollback partially fails (e.g., delete times out for 3/5 files):
# - Continues attempting to delete remaining files
# - Logs all failures
# - Returns error status with rollback attempt details
```

### Exception Propagation

```python
try:
    result = saga.execute_with_consistency(files)
    if result["status"] != "success":
        # Handle failure
except Exception as e:
    # Original exception from step failure
    # Rollback already attempted
    logger.error(f"Saga failed: {e}")
```

---

## API Endpoints Required

For full saga functionality, ensure these endpoints exist:

### Filesystem Server (`POST /save_file`)
```json
Request: {
    "project_id": "proj-123",
    "file_path": "wiki/document.md",
    "content": "..."
}
Response: {
    "status": "success",
    "file_id": "file-456",
    "path": "wiki/document.md"
}
```

### Filesystem Server (`DELETE /file/{project_id}/{filename}`)
```
DELETE /file/proj-123/document.md
X-User-ID: user-456
X-INTERNAL-TOKEN: token-789

Response: { "status": "success" }
```

### Git Server (`POST /snapshot/{project_id}`)
```json
Request: {
    "user_id": "user-456",
    "message": "Auto-generated wiki with 45 files and 128 relationships."
}
Response: {
    "snapshot_id": "snap-789",
    "project_id": "proj-123",
    "created_at": "2024-01-15T10:30:00Z"
}
```

### Git Server (`DELETE /snapshot/{project_id}/{snapshot_id}`)
```
DELETE /snapshot/proj-123/snap-789
X-User-ID: user-456
X-INTERNAL-TOKEN: token-789

Response: { "status": "success" }
```

---

## Monitoring & Alerts

### Key Metrics to Track

1. **Saga Success Rate**
   - Count successful sagas
   - Count failed sagas requiring rollback
   - Calculate: success_rate = successful / (successful + failed)

2. **Rollback Frequency**
   - How often are rollbacks triggered?
   - Indicates service stability

3. **Rollback Latency**
   - How long does rollback take?
   - Important for performance

4. **Partial Rollback Failures**
   - If any rollback step fails
   - Indicates critical issues requiring manual intervention

### Alert Conditions

Set alerts for:
- Rollback failures (immediate investigation needed)
- Consecutive saga failures (service degradation)
- Rollback latency > threshold (performance issue)

### Example Monitoring

```python
# In your monitoring system
def track_saga_event(saga_status):
    if saga_status["state"] == "rolled_back":
        metrics.increment("wiki_generation.rollbacks")
    elif saga_status["state"] == "committed":
        metrics.increment("wiki_generation.successes")
    else:
        metrics.increment("wiki_generation.failures")
```

---

## Testing

### Unit Tests

**Test 1: Successful Saga Execution**
```python
def test_successful_saga_execution():
    saga = WikiGenerationSaga(...)
    result = saga.execute_with_consistency(test_files)
    assert result["status"] == "success"
    assert result["files_created"] == len(test_files)
```

**Test 2: Rollback on Step Failure**
```python
def test_rollback_on_step_failure():
    # Mock git_server to return error
    saga = WikiGenerationSaga(...)
    result = saga.execute_with_consistency(test_files)
    assert result["status"] == "failed"
    # Verify files were deleted (cleanup)
```

**Test 3: Rollback Failure Handling**
```python
def test_rollback_failure_handling():
    # Mock delete endpoint to fail
    saga = WikiGenerationSaga(...)
    result = saga.execute_with_consistency(test_files)
    # Should still mark as failed, log errors
    assert result["status"] == "failed"
```

### Integration Tests

**Test: Full Wiki Generation with Saga**
```python
def test_full_wiki_generation_with_saga():
    project_id = "test-proj"
    user_id = "test-user"
    
    # Trigger wiki generation
    result = _run_wiki_generation_task(project_id, user_id)
    
    # Verify all steps succeeded
    assert result["files_created"] > 0
    assert result["snapshot_id"] is not None
    
    # Verify files exist
    files = filesystem_server.list_files(project_id, "wiki/")
    assert len(files) == result["files_created"]
    
    # Verify snapshot exists
    snapshot = git_server.get_snapshot(project_id, result["snapshot_id"])
    assert snapshot is not None
```

---

## Best Practices

### 1. Idempotent Rollbacks
Ensure all rollback operations are idempotent (safe to run multiple times):
```python
# ✓ GOOD: Deleting a non-existent file is safe
requests.delete(f"{url}/file/{id}")

# ✗ BAD: Would fail if file already deleted
delete_file(id)  # Raises exception if not found
```

### 2. Proper Headers
Always include internal headers for inter-service authentication:
```python
headers = {'X-User-ID': user_id}
headers.update(internal_headers)  # Includes X-INTERNAL-TOKEN
requests.post(url, headers=headers)
```

### 3. Timeout Protection
Set appropriate timeouts for each service call:
```python
# Filesystem operations: 10s
requests.delete(url, timeout=10)

# Git operations: 15s
requests.post(git_url, timeout=15)

# Network calls: 30s
requests.post(service_url, timeout=30)
```

### 4. Error Logging
Log the complete saga status on failure:
```python
except Exception as e:
    logger.error(f"Saga failed: {e}")
    logger.debug(f"Saga status: {saga.get_status()}")
```

### 5. Graceful Degradation
If individual steps aren't critical, handle them outside saga:
```python
# NOT in saga (can fail independently)
try:
    relationships = orchestrator.extract_relationships(text)
except:
    logger.warning("Relationship extraction failed, continuing")

# IN saga (must be transactional)
saga = WikiGenerationSaga(...)
result = saga.execute_with_consistency(files)
```

---

## Deployment Checklist

Before deploying saga pattern to production:

- [ ] All required endpoints exist on dependent services
- [ ] X-INTERNAL-TOKEN is set in all environments
- [ ] Monitoring and alerting configured
- [ ] Logging aggregation working
- [ ] Rollback operations tested
- [ ] Service timeouts tuned for network conditions
- [ ] Team trained on saga behavior and debugging

---

## Troubleshooting

### Problem: Sagas Failing Frequently
**Diagnosis:**
1. Check service health: Are all dependencies running?
2. Review logs for which step is failing
3. Check network connectivity

**Solution:**
- Restart failed service
- Increase timeout if network is slow
- Check service logs for errors

### Problem: Rollbacks Taking Too Long
**Diagnosis:**
1. Check DELETE endpoint performance
2. Review network latency
3. Count number of files to delete

**Solution:**
- Optimize DELETE endpoints (add indexing, batch operations)
- Consider parallel rollback instead of sequential
- Increase timeout for DELETE operations

### Problem: Orphaned Files After Rollback Failure
**Diagnosis:**
1. Check DELETE endpoint logs
2. Verify rollback was attempted
3. Identify which files weren't deleted

**Solution:**
- Manual cleanup via filesystem_server API
- Review DELETE endpoint logs for errors
- Fix underlying service issue

---

## References

- **Base Pattern Documentation:** `backend/distributed_saga.py` (DistributedSaga class)
- **Wiki-Specific Implementation:** `backend/distributed_saga.py` (WikiGenerationSaga class)
- **Integration Code:** `backend/app.py` (_run_wiki_generation_task function)
- **Related:** `SERVICE_RESILIENCE_GUIDE.md`, `SECURITY_FIX_X_USER_ID_HEADER.md`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01-15 | Initial saga pattern integration for wiki generation |

---

**Last Updated:** 2024-01-15  
**Maintained By:** Development Team  
**Status:** ✅ ACTIVE
