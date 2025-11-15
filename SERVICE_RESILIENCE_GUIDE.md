# Service Resilience & Circuit Breaker Pattern

## Overview

This guide documents the resilient service communication pattern implemented in the Caudex Pro backend. The pattern provides:

1. **Automatic Retry Logic** - Failed requests are retried with exponential backoff
2. **Circuit Breaker** - Prevents cascading failures by stopping requests to failing services
3. **Timeout Protection** - All requests have configurable timeouts
4. **Internal Token Management** - Automatic token injection for inter-service communication
5. **Comprehensive Logging** - Full observability of service communication health

## Problem Statement

### Before: Synchronous, Brittle Communication

```python
# Old pattern - no resilience
response = requests.post(
    f"{CHROMA_SERVER_URL}/query",
    json=data,
    timeout=5
)
response.raise_for_status()
```

**Issues:**
- If Chroma goes down, the entire chat request fails immediately
- No retry mechanism - transient failures cause cascading failures
- No circuit breaker - multiple failed requests hammer a downed service
- No backoff - rapid retries can overwhelm recovering services
- Poor observability - hard to diagnose service communication issues

### After: Resilient Service Communication

```python
# New pattern - with resilience
chroma_client = ResilientServiceClient(
    CHROMA_SERVER_URL,
    service_name="Chroma Server",
    max_retries=3,
    timeout=10
)

try:
    response = chroma_client.post("/query", json=data)
    results = response.json()
except ServiceUnavailable:
    # Circuit breaker is open - service is down
    logger.error("Chroma is down, using fallback search")
    results = fallback_search(data)
except requests.RequestException as e:
    # Request failed after all retries
    logger.error(f"Chroma query failed: {e}")
    return jsonify({"error": "Search unavailable"}), 503
```

**Improvements:**
- Automatic retries with exponential backoff (1s, 2s, 4s)
- Circuit breaker prevents hammering downed services
- Graceful degradation with fallback strategies
- Full observability via detailed logging

## Circuit Breaker States

The circuit breaker operates in three states:

### CLOSED (Normal)
- **Behavior**: Requests pass through normally
- **Failure Handling**: Retries are attempted
- **Transition**: Opens after 5 consecutive failures (configurable)
- **Use Case**: Service is healthy

```
Request → [Retry logic] → Success → CLOSED (continue)
Request → [Retry logic] → Failure × 5 → OPEN
```

### OPEN (Service Down)
- **Behavior**: All requests immediately fail with `ServiceUnavailable`
- **Purpose**: Prevent hammering a failing service
- **Transition**: Moves to HALF_OPEN after recovery timeout (60s default)
- **Logging**: Warnings logged when requests rejected

```
Request → ServiceUnavailable (immediately, no retries)
[Wait 60s] → HALF_OPEN
```

### HALF_OPEN (Testing Recovery)
- **Behavior**: Attempts request to test if service recovered
- **Success**: Returns to CLOSED state
- **Failure**: Returns to OPEN state, resets timer
- **Purpose**: Automatically recover when service comes back online

```
Request → [Single attempt, no retries] → Success → CLOSED
Request → [Single attempt, no retries] → Failure → OPEN
```

## Implementation

### Creating Resilient Clients

Initialize one client per service and reuse it:

```python
# Initialize clients at module level (backend/app.py)
from service_utils import ResilientServiceClient

chroma_client = ResilientServiceClient(
    os.getenv("CHROMA_SERVER_URL", "http://chroma:6003"),
    service_name="Chroma Server",
    max_retries=3,
    timeout=10
)

filesystem_client = ResilientServiceClient(
    os.getenv("FILESYSTEM_SERVER_URL", "http://filesystem:6002"),
    service_name="Filesystem Server",
    max_retries=3,
    timeout=15
)

billing_client = ResilientServiceClient(
    os.getenv("BILLING_SERVER_URL", "http://billing:6004"),
    service_name="Billing Server",
    max_retries=2,
    timeout=5
)

git_client = ResilientServiceClient(
    os.getenv("GIT_SERVER_URL", "http://git:6005"),
    service_name="Git Server",
    max_retries=3,
    timeout=30
)
```

### Using Resilient Clients

#### GET Request

```python
try:
    response = chroma_client.get(
        "/ready",
        timeout=5
    )
    if response.status_code == 200:
        logger.info("Chroma is ready")
except ServiceUnavailable:
    logger.error("Chroma circuit breaker open")
except requests.RequestException as e:
    logger.error(f"Chroma health check failed: {e}")
```

#### POST Request with JSON

```python
try:
    response = chroma_client.post(
        "/query",
        json={
            "collection_name": "project_123",
            "query_texts": ["what is AI?"],
            "n_results": 5
        }
    )
    results = response.json()
except ServiceUnavailable:
    logger.error("Chroma down, using cached results")
    results = cache.get("fallback_results")
except requests.RequestException as e:
    logger.error(f"Query failed: {e}")
    return jsonify({"error": "Search service unavailable"}), 503
```

#### Chaining Operations with Fallback

```python
def chat_with_resilience(query, user_id):
    """Chat endpoint with graceful degradation."""
    try:
        # Try to get vector search results
        search_response = chroma_client.post(
            "/query",
            json={"collection_name": f"project_{project_id}", "query_texts": [query]}
        )
        context = search_response.json()
    except (ServiceUnavailable, requests.RequestException) as e:
        logger.warning(f"Vector search unavailable: {e}, using basic search")
        context = basic_search(query)
    
    # Continue with chat
    response = llm.generate_response(query, context)
    
    try:
        # Try to save to filesystem
        filesystem_client.post(
            "/save_file",
            json={
                "project_id": project_id,
                "file_path": "chat_history.md",
                "content": response
            }
        )
    except ServiceUnavailable:
        logger.warning("Filesystem service down, continuing without save")
    except requests.RequestException as e:
        logger.warning(f"Failed to save: {e}")
    
    return response
```

## Migration Guide

### Step 1: Initialize Resilient Clients in Backend

In `backend/app.py` (near the top with other imports):

```python
from service_utils import ResilientServiceClient, ServiceUnavailable

# Initialize resilient clients for each service
chroma_client = ResilientServiceClient(
    os.getenv("CHROMA_SERVER_URL", "http://chroma:6003"),
    service_name="Chroma Server"
)

filesystem_client = ResilientServiceClient(
    os.getenv("FILESYSTEM_SERVER_URL", "http://filesystem:6002"),
    service_name="Filesystem Server"
)

billing_client = ResilientServiceClient(
    os.getenv("BILLING_SERVER_URL", "http://billing:6004"),
    service_name="Billing Server"
)

git_client = ResilientServiceClient(
    os.getenv("GIT_SERVER_URL", "http://git:6005"),
    service_name="Git Server"
)
```

### Step 2: Replace Direct requests.post() Calls

**Before:**
```python
resp = requests.post(
    f"{CHROMA_SERVER_URL}/add",
    json=data,
    headers=get_internal_headers(),
    timeout=10
)
resp.raise_for_status()
```

**After:**
```python
try:
    resp = chroma_client.post("/add", json=data)
    # Internal token headers are automatically added
except ServiceUnavailable:
    logger.error("Chroma is down")
    return jsonify({"error": "Database service unavailable"}), 503
except requests.RequestException as e:
    logger.error(f"Chroma request failed: {e}")
    return jsonify({"error": "Database request failed"}), 503
```

### Step 3: Handle Circuit Breaker States

Add application-level fallback logic:

```python
@app.route('/v1/api/search', methods=['POST'])
def search():
    query = request.json.get('query')
    
    try:
        # Try primary search in Chroma
        response = chroma_client.post("/query", json={"query_texts": [query]})
        return response.json(), 200
    except ServiceUnavailable:
        logger.warning("Vector search unavailable, using fallback")
        # Implement fallback search (full-text, cached results, etc.)
        fallback_results = fallback_search(query)
        return fallback_results, 200
    except requests.RequestException as e:
        logger.error(f"Search failed: {e}")
        return {"error": "Search service temporarily unavailable"}, 503
```

## Configuration

### Client Parameters

```python
ResilientServiceClient(
    base_url="http://service:port",           # Service URL
    service_name="Service Name",              # For logging
    max_retries=3,                            # Retry attempts (default 3)
    timeout=10,                               # Request timeout in seconds (default 10)
    failure_threshold=5,                      # Failures before circuit opens (default 5)
    recovery_timeout=60                       # Seconds before recovery attempt (default 60)
)
```

### Recommended Configurations by Service

**Chroma (Vector Search)**
```python
chroma_client = ResilientServiceClient(
    CHROMA_SERVER_URL,
    service_name="Chroma Server",
    max_retries=3,              # Vector ops can be slow
    timeout=15,
    failure_threshold=5,        # More tolerant
    recovery_timeout=60
)
```

**Filesystem (File Operations)**
```python
filesystem_client = ResilientServiceClient(
    FILESYSTEM_SERVER_URL,
    service_name="Filesystem Server",
    max_retries=3,
    timeout=20,                 # File I/O can be slower
    failure_threshold=5,
    recovery_timeout=60
)
```

**Billing (Fast Operations)**
```python
billing_client = ResilientServiceClient(
    BILLING_SERVER_URL,
    service_name="Billing Server",
    max_retries=2,              # Fast operation, fewer retries
    timeout=5,                  # Short timeout
    failure_threshold=10,       # More tolerant
    recovery_timeout=30         # Faster recovery
)
```

**Git (Potentially Slow)**
```python
git_client = ResilientServiceClient(
    GIT_SERVER_URL,
    service_name="Git Server",
    max_retries=3,
    timeout=30,                 # Git operations can be slow
    failure_threshold=5,
    recovery_timeout=90         # Longer timeout for complex operations
)
```

## Monitoring & Observability

### Get Circuit Breaker Status

```python
# In a monitoring endpoint
@app.route('/v1/api/status/services', methods=['GET'])
def service_status():
    return jsonify({
        "chroma": chroma_client.get_status(),
        "filesystem": filesystem_client.get_status(),
        "billing": billing_client.get_status(),
        "git": git_client.get_status()
    }), 200
```

### Log Interpretation

**Healthy Service (CLOSED state):**
```
[Service Name] GET /query (attempt 1/3)
[Service Name] ✓ GET /query succeeded
```

**Transient Failure with Recovery:**
```
[Service Name] POST /add (attempt 1/3)
[Service Name] Connection failed on attempt 1/3: Connection refused
[Service Name] Retrying in 1s...
[Service Name] POST /add (attempt 2/3)
[Service Name] ✓ POST /add succeeded
```

**Circuit Breaker Opening:**
```
[Service Name] POST /update (attempt 1/3)
[Service Name] Server error 500 on attempt 1/3
[Service Name] Retrying in 1s...
[Service Name] POST /update (attempt 2/3)
[Service Name] Server error 500 on attempt 2/3
[Service Name] Retrying in 2s...
[Service Name] POST /update (attempt 3/3)
[Service Name] Server error 500 on attempt 3/3
[Service Name] ✗ All 3 retry attempts failed
[Service Name] Circuit breaker OPEN (threshold reached: 5/5)
```

**Circuit Breaker Rejecting Requests:**
```
[Service Name] Circuit breaker OPEN - rejecting request
```

**Successful Recovery:**
```
[Service Name] Circuit breaker entering HALF_OPEN state
[Service Name] GET /health (attempt 1/3)
[Service Name] ✓ GET /health succeeded
[Service Name] Circuit breaker CLOSED (service recovered)
```

## Error Handling Patterns

### Pattern 1: Fail Open (With Fallback)

Use when fallback is available:

```python
try:
    response = chroma_client.post("/query", json=query_data)
    results = response.json()
except (ServiceUnavailable, requests.RequestException):
    logger.warning("Using fallback search")
    results = fallback_search()
```

### Pattern 2: Fail Closed (Return Error)

Use when operation cannot proceed without service:

```python
try:
    response = billing_client.post("/deduct_cost", json={"amount": 100})
    response.raise_for_status()
except ServiceUnavailable:
    logger.error("Billing service unavailable")
    return jsonify({"error": "Cannot process billing"}), 503
except requests.RequestException as e:
    logger.error(f"Billing failed: {e}")
    return jsonify({"error": "Billing service error"}), 503
```

### Pattern 3: Best Effort (Log and Continue)

Use for non-critical operations:

```python
try:
    git_client.post(
        f"/snapshot/{project_id}",
        json={"message": "Auto-save"}
    )
except ServiceUnavailable:
    logger.warning("Git service down, skipping snapshot")
except requests.RequestException as e:
    logger.warning(f"Failed to create snapshot: {e}")
# Continue regardless
```

## Testing

### Test Circuit Breaker Behavior

```python
# test_resilience.py
import pytest
from service_utils import ResilientServiceClient, ServiceUnavailable
from unittest.mock import patch, MagicMock

def test_circuit_breaker_opens_after_failures():
    """Test that circuit breaker opens after threshold failures."""
    client = ResilientServiceClient(
        "http://failing-service:9999",
        failure_threshold=3,
        max_retries=1
    )
    
    with patch('requests.request') as mock_request:
        mock_request.side_effect = ConnectionError("Service down")
        
        # First 3 failures trigger circuit open
        for i in range(3):
            with pytest.raises(ConnectionError):
                client.post("/test")
        
        # Circuit is now open
        assert client.state.value == "open"
        
        # Next request fails immediately
        with pytest.raises(ServiceUnavailable):
            client.post("/test")

def test_circuit_breaker_recovers():
    """Test that circuit breaker recovers after timeout."""
    client = ResilientServiceClient(
        "http://service:9999",
        failure_threshold=2,
        recovery_timeout=1,
        max_retries=1
    )
    
    with patch('requests.request') as mock_request:
        # Trigger circuit open
        mock_request.side_effect = ConnectionError()
        for _ in range(2):
            with pytest.raises(ConnectionError):
                client.post("/test")
        
        assert client.state.value == "open"
        
        # Wait for recovery timeout
        import time
        time.sleep(1.1)
        
        # Next request attempts (enters HALF_OPEN)
        mock_request.side_effect = None
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        
        response = client.post("/test")
        assert response.status_code == 200
        assert client.state.value == "closed"
```

## Best Practices

1. **Initialize Once, Reuse Many Times**
   ```python
   # Good: Create at module level
   chroma_client = ResilientServiceClient(CHROMA_URL)
   
   # Bad: Create in every request
   def my_route():
       client = ResilientServiceClient(CHROMA_URL)  # Don't do this
   ```

2. **Always Handle Both Exceptions**
   ```python
   try:
       response = client.post("/endpoint", json=data)
   except ServiceUnavailable:
       # Circuit breaker is open
       pass
   except requests.RequestException:
       # Other errors (timeout, connection, HTTP errors)
       pass
   ```

3. **Use Appropriate Timeouts**
   - Quick operations (billing): 5-10 seconds
   - Medium operations (filesystem): 10-20 seconds
   - Slow operations (vector search, git): 20-30 seconds

4. **Tune Failure Threshold Per Service**
   - Non-critical services: Higher threshold (10+)
   - Critical path services: Lower threshold (3-5)

5. **Implement Fallback Strategies**
   - Vector search → Full-text search
   - Slow operations → Cached results
   - Filesystem → In-memory storage

6. **Monitor Circuit Breaker States**
   - Add a health endpoint to check service status
   - Alert when circuit opens
   - Track mean time to recovery (MTTR)

## See Also

- `backend/service_utils.py` - Complete implementation
- `ENVIRONMENT_VARIABLES.md` - Service URL configuration
- `PRODUCTION_DEPLOYMENT.md` - Deployment guidelines
