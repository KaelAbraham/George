# Saga Pattern Quick Reference

## TL;DR

The **Saga Pattern** ensures distributed transactions are **all-or-nothing** across microservices:
- If any step fails → all previous steps are automatically rolled back
- No orphaned data, consistent state guaranteed

---

## Quick Start

### Using WikiGenerationSaga

```python
from distributed_saga import WikiGenerationSaga
from service_utils import get_internal_headers

# Create saga
saga = WikiGenerationSaga(
    project_id="proj-123",
    user_id="user-456",
    filesystem_url="http://localhost:6001",
    git_url="http://localhost:6003",
    internal_headers=get_internal_headers()
)

# Execute with automatic rollback on failure
try:
    result = saga.execute_with_consistency(generated_files)
    if result["status"] == "success":
        print(f"✓ Created {result['files_created']} files")
        print(f"✓ Snapshot: {result['snapshot_id']}")
    else:
        print(f"✗ Failed: {result['error']}")
        print(f"  Rolled back: {result['saga_status']}")
except Exception as e:
    print(f"✗ Exception: {e}")
```

### Creating Custom Saga

```python
from distributed_saga import DistributedSaga

saga = DistributedSaga(saga_id="operation-123", user_id="user-456")

try:
    # Step 1: Do something
    result1 = saga.execute_step(
        name="Step 1: Create resource",
        action=lambda: create_resource(),
        rollback=lambda: delete_resource()
    )
    
    # Step 2: Do something else
    result2 = saga.execute_step(
        name="Step 2: Update resource",
        action=lambda: update_resource(result1),
        rollback=lambda: revert_resource(result1)
    )
    
    # All steps succeeded
    saga.commit()
    print("✓ Saga completed successfully")
    
except Exception as e:
    # Rollback happened automatically
    print(f"✗ Saga failed: {e}")
    print(f"  Status: {saga.get_status()}")
```

---

## API Reference

### DistributedSaga

```python
# Create saga
saga = DistributedSaga(
    saga_id="unique-id",      # For logging
    user_id="user-id"         # For audit
)

# Execute a step
result = saga.execute_step(
    name="Step description",
    action=lambda: perform_operation(),
    rollback=lambda: undo_operation()
)

# Mark complete
saga.commit()

# Get status
status = saga.get_status()
```

**States:** PENDING → EXECUTING → COMMITTED (or ROLLED_BACK/FAILED)

### WikiGenerationSaga

```python
saga = WikiGenerationSaga(
    project_id="proj-id",
    user_id="user-id",
    filesystem_url="http://fs:6001",
    git_url="http://git:6003",
    internal_headers={"X-INTERNAL-TOKEN": "token"}
)

# Execute full transaction
result = saga.execute_with_consistency(generated_files)

# result = {
#     "status": "success" | "failed",
#     "files_created": int,
#     "snapshot_id": str,
#     "error": str (if failed),
#     "saga_status": dict,
#     "message": str
# }
```

---

## Saga States

| State | Description | Rollback? |
|-------|-------------|-----------|
| PENDING | Initial state, no steps started | No |
| EXECUTING | Currently executing a step | Partial (only completed) |
| COMMITTED | All steps successful | No (complete) |
| ROLLED_BACK | Failed and rolled back | Yes (all) |
| FAILED | Rolled back but with errors | Partial |

---

## Execution Flow

### Success Path
```
Step 1 ✓ → Step 2 ✓ → Step 3 ✓ → commit() → SUCCESS
```

### Failure Path
```
Step 1 ✓ → Step 2 ✓ → Step 3 ✗ 
  ↓
[Automatic Rollback]
  ↓
Step 2 rollback ✓ → Step 1 rollback ✓ → FAILURE
```

---

## Common Patterns

### All-or-Nothing Multi-Service Operation

```python
saga = DistributedSaga("multi-svc")

# Service 1
result1 = saga.execute_step(
    name="Call service 1",
    action=lambda: requests.post(url1, json=data),
    rollback=lambda: requests.delete(url1 + "/undo")
)

# Service 2
result2 = saga.execute_step(
    name="Call service 2",
    action=lambda: requests.post(url2, json=data),
    rollback=lambda: requests.delete(url2 + "/undo")
)

saga.commit()
```

### Nested Data Creation with Rollback

```python
created_ids = []

def create_and_track():
    id = create_resource()
    created_ids.append(id)
    return id

def delete_all():
    for id in created_ids:
        delete_resource(id)

result = saga.execute_step(
    name="Create resources",
    action=create_and_track,
    rollback=delete_all
)
```

### Conditional Steps

```python
if should_do_step1:
    saga.execute_step(...)

if should_do_step2:
    saga.execute_step(...)

saga.commit()
```

---

## Error Handling

### Explicit Error Handling

```python
try:
    result = saga.execute_with_consistency(files)
except Exception as e:
    if "timeout" in str(e):
        logger.error("Service timeout, all changes rolled back")
    elif "unauthorized" in str(e):
        logger.error("Authorization failed")
    else:
        logger.error(f"Unknown error: {e}")
```

### Rollback Failure Detection

```python
result = saga.execute_with_consistency(files)

if result["status"] == "failed":
    saga_status = result.get("saga_status", {})
    if saga_status.get("state") == "failed":  # Not rolled back properly
        logger.critical("MANUAL CLEANUP REQUIRED!")
        logger.critical(f"Saga: {saga_status}")
```

---

## Debugging

### Enable Debug Logging

```python
import logging
logging.getLogger("distributed_saga").setLevel(logging.DEBUG)
```

### View Saga Status Anytime

```python
status = saga.get_status()
print(status)
# {
#     "saga_id": "wiki-proj-123",
#     "user_id": "user-456",
#     "state": "executing",
#     "total_steps": 3,
#     "completed_steps": 2,
#     "failed_at": None,
#     "error": None
# }
```

### Check Which Step Failed

```python
except Exception:
    status = saga.get_status()
    failed_at = status.get("failed_at")
    error = status.get("error")
    print(f"Failed at: {failed_at}")
    print(f"Error: {error}")
```

---

## Best Practices

✅ **DO:**
- Use for distributed transactions that must be consistent
- Make rollback actions idempotent (safe to run multiple times)
- Include error handling and logging
- Set appropriate timeouts per service
- Test rollback scenarios

❌ **DON'T:**
- Use for operations that can't be rolled back (e.g., sending emails)
- Skip error handling
- Use overly long timeout values
- Forget to test failure scenarios
- Create circular dependencies between steps

---

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Files not deleted during rollback | Delete endpoint timing out | Increase timeout, check endpoint |
| Saga never completes | Deadlock between services | Check service logs, restart |
| Frequent rollbacks | Service unstable | Check service health, review logs |
| Slow rollback | Too many files | Optimize delete, consider pagination |

---

## Performance Tips

1. **Parallel Rollback:** Instead of sequential, run rollbacks in parallel
   ```python
   # Current: Sequential
   # New: Could use asyncio for parallel rollbacks
   ```

2. **Batch Operations:** Delete multiple files in one request
   ```python
   # Current: Delete one file per request
   # New: POST /delete_batch with file list
   ```

3. **Timeout Tuning:** Set realistic timeouts per service
   - Quick operations: 5-10s
   - File operations: 10-15s
   - Network calls: 20-30s

---

## Monitoring

```python
# Track saga outcomes
saga_success_count = 0
saga_failure_count = 0

try:
    result = saga.execute_with_consistency(files)
    if result["status"] == "success":
        saga_success_count += 1
    else:
        saga_failure_count += 1
except:
    saga_failure_count += 1

# Compute metrics
success_rate = saga_success_count / (saga_success_count + saga_failure_count)
print(f"Saga success rate: {success_rate:.2%}")
```

---

## See Also

- **Full Guide:** `SAGA_PATTERN_INTEGRATION.md`
- **Service Resilience:** `SERVICE_RESILIENCE_GUIDE.md`
- **Security:** `SECURITY_FIX_X_USER_ID_HEADER.md`
- **Source Code:** `backend/distributed_saga.py`

---

**Last Updated:** 2024-01-15  
**Status:** ✅ ACTIVE
