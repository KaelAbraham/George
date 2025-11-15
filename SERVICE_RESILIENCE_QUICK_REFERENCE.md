# Service Resilience Quick Reference

## One-Line Summary

**ResilientServiceClient** implements circuit breaker pattern with automatic retry logic to prevent cascading failures when microservices are down.

## Quick Start (Copy-Paste)

### 1. Import and Initialize

```python
from service_utils import ResilientServiceClient, ServiceUnavailable

chroma_client = ResilientServiceClient(
    os.getenv("CHROMA_SERVER_URL", "http://chroma:6003"),
    service_name="Chroma Server"
)
```

### 2. Use in Code

```python
try:
    response = chroma_client.post("/query", json=data)
    results = response.json()
except ServiceUnavailable:
    logger.error("Chroma is down")
    results = fallback_search()
except requests.RequestException as e:
    logger.error(f"Search failed: {e}")
    return {"error": "Service unavailable"}, 503
```

### 3. Monitor Status

```python
@app.route('/v1/api/status/services', methods=['GET'])
def service_status():
    return {
        "chroma": chroma_client.get_status(),
        "filesystem": filesystem_client.get_status()
    }
```

## Methods

| Method | Example | Purpose |
|--------|---------|---------|
| `.post()` | `client.post("/endpoint", json=data)` | POST request with retry |
| `.get()` | `client.get("/health")` | GET request with retry |
| `.put()` | `client.put("/update", json=data)` | PUT request with retry |
| `.delete()` | `client.delete("/item/123")` | DELETE request with retry |
| `.get_status()` | `client.get_status()` | Get circuit breaker state |

## Exception Handling

```python
try:
    response = client.post("/endpoint", json=data)
except ServiceUnavailable:
    # Circuit breaker is open - service is failing
    # Use fallback or cached data
    pass
except requests.RequestException as e:
    # Transient error (timeout, connection, etc.)
    # Service may be temporarily unavailable
    pass
except Exception as e:
    # Unexpected error
    pass
```

## Configuration Presets

### For Slow Operations (Vector Search, File I/O)

```python
client = ResilientServiceClient(url, max_retries=3, timeout=15)
```

### For Fast Operations (Billing, Auth)

```python
client = ResilientServiceClient(url, max_retries=2, timeout=5)
```

### For Complex Operations (Git)

```python
client = ResilientServiceClient(
    url, 
    max_retries=3, 
    timeout=30,
    recovery_timeout=90
)
```

## Circuit Breaker States

| State | Behavior | Transition |
|-------|----------|-----------|
| **CLOSED** | Requests pass, retries on failure | → OPEN after 5 failures |
| **OPEN** | Requests rejected immediately | → HALF_OPEN after 60s |
| **HALF_OPEN** | Single test request | → CLOSED (success) or OPEN (fail) |

## Retry Pattern

```
Attempt 1 → Fail → Wait 1s  ✓
Attempt 2 → Fail → Wait 2s  ✓
Attempt 3 → Fail → Raise    ✗
```

Exponential backoff: 1s, 2s, 4s, 8s...

## Status Endpoint Response

```json
{
  "service": "Chroma Server",
  "state": "closed|open|half_open",
  "failure_count": 0,
  "last_failure": "2025-11-15T10:32:12Z" | null,
  "last_state_change": "2025-11-15T10:30:45Z"
}
```

## Common Patterns

### Fail Open (Use Fallback)
```python
try:
    results = chroma_client.post("/query", json=data)
except (ServiceUnavailable, requests.RequestException):
    results = fallback_search()
```

### Fail Closed (Return Error)
```python
try:
    billing_client.post("/charge", json=data)
except (ServiceUnavailable, requests.RequestException) as e:
    return {"error": "Cannot process"}, 503
```

### Best Effort (Log and Continue)
```python
try:
    git_client.post("/snapshot", json=data)
except (ServiceUnavailable, requests.RequestException) as e:
    logger.warning(f"Snapshot failed: {e}")
# Continue regardless
```

## Logging Output

```
✓ Healthy:      [Service] ✓ GET /endpoint succeeded
⚠ Retry:        [Service] Connection failed on attempt 1/3, retrying in 1s...
✗ Circuit Open: [Service] Circuit breaker OPEN (threshold reached)
🔄 Recovery:    [Service] Circuit breaker CLOSED (service recovered)
```

## Initialization Checklist

- [ ] Import: `from service_utils import ResilientServiceClient, ServiceUnavailable`
- [ ] Create client at module level (not in function)
- [ ] Use in try/except block
- [ ] Handle both `ServiceUnavailable` and `requests.RequestException`
- [ ] Implement fallback strategy if available
- [ ] Add monitoring endpoint to check status
- [ ] Test circuit breaker behavior
- [ ] Set appropriate timeout for service type

## Integration Steps

1. **Replace direct requests:**
   ```python
   # Old
   resp = requests.post(f"{URL}/endpoint", json=data)
   
   # New
   resp = client.post("/endpoint", json=data)
   ```

2. **Add error handling:**
   ```python
   try:
       resp = client.post("/endpoint", json=data)
   except (ServiceUnavailable, requests.RequestException) as e:
       # Handle error
   ```

3. **Add monitoring:**
   ```python
   @app.route('/status/services')
   def status():
       return jsonify({"chroma": chroma_client.get_status()})
   ```

## Performance Impact

| Scenario | Before | After | Improvement |
|----------|--------|-------|-------------|
| Service Down | 30s timeout × 3 = 90s | Circuit opens in ~7s | 12× faster |
| Transient Failure | Immediate fail | Auto-retry | Success rate ↑ |
| Recovery | Manual restart | Auto-detect | Automatic |

## Files Reference

| File | Purpose |
|------|---------|
| `backend/service_utils.py` | Core implementation (ResilientServiceClient) |
| `SERVICE_RESILIENCE_GUIDE.md` | Complete design guide |
| `SERVICE_RESILIENCE_EXAMPLES.md` | Code examples and patterns |
| `SERVICE_RESILIENCE_SUMMARY.md` | Implementation overview |
| `SERVICE_ARCHITECTURE.md` | Architecture diagrams and flow |

## Related Concepts

- **Circuit Breaker Pattern** - Prevent cascading failures
- **Exponential Backoff** - Wait longer between retries
- **Timeout** - Prevent hanging indefinitely
- **Fallback Strategy** - Use alternative when primary fails
- **Health Check** - Determine service readiness

## Deployment

### Development
```python
client = ResilientServiceClient(
    "http://chroma:6003",
    max_retries=3,
    timeout=10
)
```

### Production
```python
client = ResilientServiceClient(
    os.getenv("CHROMA_SERVER_URL"),  # From env var
    max_retries=3,
    timeout=10,
    failure_threshold=5,
    recovery_timeout=60
)
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Circuit breaker open" | Service is failing, wait for recovery or restart service |
| "All retries failed" | Check service URL, network connectivity, service health |
| "Timeout" | Increase timeout if service is slow, or check service performance |
| "HTTP 4xx errors" | Check request format, auth tokens, request validation |

## Key Parameters

```python
ResilientServiceClient(
    base_url="http://service:port",    # Service address
    service_name="Service",             # For logging
    max_retries=3,                      # Retry attempts
    timeout=10,                         # Request timeout (seconds)
    failure_threshold=5,                # Failures to open circuit
    recovery_timeout=60                 # Seconds before testing recovery
)
```

## Testing

```python
# Mock failure
with patch('requests.request') as mock:
    mock.side_effect = ConnectionError()
    with pytest.raises(ServiceUnavailable):
        client.post("/endpoint")

# Mock success
with patch('requests.request') as mock:
    mock.return_value = MagicMock(status_code=200)
    response = client.post("/endpoint")
    assert response.status_code == 200
```

## Latest Commits

- `10d03b8` - Service architecture documentation
- `aea5920` - Implementation summary
- `7c9b199` - Core ResilientServiceClient implementation
- `e9455c4` - Debug verification report
- `8a3ce53` - Enhanced Chroma health endpoint

---

**Status**: ✅ Production Ready

Start using: Copy initialization code above and replace `requests.post()` calls with `client.post()`.
