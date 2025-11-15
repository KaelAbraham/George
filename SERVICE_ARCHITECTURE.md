# Service Communication Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                        Frontend (React)                         │
│                     https://app.caudex.pro                      │
│                                                                 │
└────────────┬────────────────────────────────────────────────────┘
             │
             │ HTTPS (Bearer Token / Cookie)
             │
┌────────────▼────────────────────────────────────────────────────┐
│                                                                 │
│              Backend Server (Port 5000)                         │
│           ┌───────────────────────────────────┐                │
│           │   Flask App with Resilience      │                │
│           │                                   │                │
│           │  /v1/api/chat                    │                │
│           │  /v1/api/search                  │                │
│           │  /v1/api/status/services         │                │
│           └───────────────────────────────────┘                │
│                                                                 │
└────────┬──────────────┬──────────────┬──────────────┬───────────┘
         │              │              │              │
         │              │              │              │
    INTERNAL TOKEN (X-INTERNAL-TOKEN header)
         │              │              │              │
         │              │              │              │
    ┌────▼────┐    ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
    │  Auth   │    │ Chroma  │   │FileSystem   │Git │
    │ Server  │    │ Server  │   │ Server  │Server
    │(6001)   │    │(6003)   │   │(6002)   │(6005)
    └─────────┘    └─────────┘   └─────────┘└─────┘
         │              │              │         │
    ┌────▼────────┐  ┌──▼──────┐  ┌───▼─────┐  │
    │  Firebase   │  │ ChromaDB │  │ Local   │  │
    │             │  │ Persist  │  │ Storage │  │
    └─────────────┘  └──────────┘  └─────────┘  │
                                                  │
         ┌────────────────────────────────────────┘
         │
    ┌────▼──────────┐
    │ Neo4j Graph DB│
    │ (Port 7687)   │
    └───────────────┘
```

## Service Communication Flow with Resilience

### Request Flow Diagram

```
1. User Request
       │
       ▼
┌─────────────────────────────────────────────┐
│  Backend Receives Request                   │
│  GET /v1/api/chat { message: "hello" }     │
└─────────────────────────────────────────────┘
       │
       ├─────────────────────────────────────┐
       │                                     │
       ▼                                     │
┌─────────────────────────────┐              │
│  Get Context from Chroma    │              │
│  (Primary Strategy)         │              │
└─────────────────────────────┘              │
       │                                     │
       ├─ [Resilient Client]                │
       │  ├─ Request 1 → TIMEOUT            │
       │  ├─ Wait 1s                        │
       │  ├─ Request 2 → SUCCESS ✓          │
       │  └─ Return Results                 │
       │                                     │
       ├─────── On Failure ─────┐            │
       │                        │            │
       ▼                        │            │
   [Circuit State]              │            │
   - If OPEN                    │            │
     └─ Raise ServiceUnavailable │            │
                                ▼            │
                    ┌────────────────────┐   │
                    │ Use Fallback Search│   │
                    │ (Full-text, cache) │   │
                    └────────────────────┘   │
                                             │
       ┌─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│  Generate Response with LLM                 │
│  ├─ Combine Query + Context                │
│  └─ Stream Response to User                │
└─────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│  Save to Filesystem (Best Effort)           │
│  ├─ [Resilient Client]                      │
│  └─ If fails → Log warning, continue       │
└─────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│  Return Response to Frontend                │
│  { response: "answer...", status: 200 }    │
└─────────────────────────────────────────────┘
```

## Circuit Breaker State Machine

```
                    ┌─────────────────┐
                    │  Initialization │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   CLOSED        │
                    │ Service Healthy │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         Success      Failure   Failure
             │            │ × 5  │
             │            │      │
             ▼            ▼      ▼
        ✓ Reset        ┌─────────────────┐
        ✓ Continue     │   OPEN          │
                       │  (Failing)      │
                       │                 │
                       │ Reject all      │
                       │ requests        │
                       └────────┬────────┘
                                │
                        Wait 60s (recovery_timeout)
                                │
                                ▼
                       ┌─────────────────┐
                       │  HALF_OPEN      │
                       │ (Testing)       │
                       └────────┬────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                Success              Failure
                    │                       │
                    ▼                       ▼
              ┌─────────────┐         ┌─────────────┐
              │  CLOSED     │         │  OPEN       │
              │ ✓ Recovered │         │ Reset Timer │
              └─────────────┘         └─────────────┘
                                            │
                                    Wait 60s
                                            │
                                            └─► HALF_OPEN
```

## Client Initialization Pattern

```python
# backend/app.py

from service_utils import ResilientServiceClient

# Initialize at module level (create once, reuse many times)
chroma_client = ResilientServiceClient(
    base_url=os.getenv("CHROMA_SERVER_URL", "http://chroma:6003"),
    service_name="Chroma Server",
    max_retries=3,              # 1s, 2s, 4s backoff
    timeout=10,                 # 10 second timeout
    failure_threshold=5,        # Open after 5 failures
    recovery_timeout=60         # Test recovery after 60s
)

filesystem_client = ResilientServiceClient(
    base_url=os.getenv("FILESYSTEM_SERVER_URL", "http://filesystem:6002"),
    service_name="Filesystem Server",
    max_retries=3,
    timeout=15,                 # File ops are slower
    failure_threshold=5,
    recovery_timeout=60
)

billing_client = ResilientServiceClient(
    base_url=os.getenv("BILLING_SERVER_URL", "http://billing:6004"),
    service_name="Billing Server",
    max_retries=2,              # Fast ops, fewer retries
    timeout=5,
    failure_threshold=10,
    recovery_timeout=30         # Faster recovery
)

git_client = ResilientServiceClient(
    base_url=os.getenv("GIT_SERVER_URL", "http://git:6005"),
    service_name="Git Server",
    max_retries=3,
    timeout=30,                 # Git can be slow
    failure_threshold=5,
    recovery_timeout=90         # Give git more time
)
```

## Error Handling Decision Tree

```
                    Service Call
                         │
                         ▼
                  [Resilient Client]
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    Success         ServiceUnavailable   Other Exception
        │         (Circuit Open)         (Retry Failed)
        │                │                │
        ▼                ▼                ▼
    Continue        Is fallback?     Is critical?
        │            available?      operation?
        │                │                │
        ├─ Yes, Y          ├─ No
        │    │                  ├─ Y  ├─ N
        ▼    ▼                  ▼  ▼
    Return  Use         Log    Return  Log
    Result  Fallback    Error  503     Warning
                        Warn         Continue
```

## Retry Logic Flow

```
Request #1
    │
    ├─ Success ✓ → Return (failure_count = 0)
    │
    ├─ Timeout → Log warning, failure_count++
    │         └─ Sleep 1s (2^0)
    │
    └─ Failure → Log warning, failure_count++
                 │
                 ├─ If threshold reached → Open circuit
                 │
                 └─ Sleep 1s (2^0) → Request #2
                                        │
                                        ├─ Success ✓ → Return
                                        │
                                        ├─ Timeout → Log warning
                                        │         └─ Sleep 2s (2^1)
                                        │
                                        └─ Failure → Sleep 2s (2^1) → Request #3
                                                        │
                                                        ├─ Success ✓ → Return
                                                        │
                                                        ├─ Timeout → Log ERROR
                                                        │         └─ Raise Timeout
                                                        │
                                                        └─ Failure → Raise RequestException
```

## Monitoring and Observability

### Health Status Endpoint

```
GET /v1/api/status/services

Response:
{
  "services": {
    "chroma": {
      "service": "Chroma Server",
      "state": "closed|open|half_open",
      "failure_count": 0,
      "last_failure": "2025-11-15T10:32:12.456789" | null,
      "last_state_change": "2025-11-15T10:30:45.123456"
    },
    "filesystem": { ... },
    "billing": { ... },
    "git": { ... }
  },
  "timestamp": "2025-11-15T10:33:00.000000"
}
```

### Logging Output

```
NORMAL (CLOSED):
[Chroma Server] GET /health (attempt 1/3)
[Chroma Server] ✓ GET /health succeeded

TRANSIENT FAILURE (RETRY):
[Chroma Server] POST /query (attempt 1/3)
[Chroma Server] Connection failed on attempt 1/3: Connection refused
[Chroma Server] Retrying in 1s...
[Chroma Server] POST /query (attempt 2/3)
[Chroma Server] ✓ POST /query succeeded

CASCADING FAILURE (CIRCUIT OPEN):
[Chroma Server] POST /query (attempt 1/3)
[Chroma Server] Server error 500 on attempt 1/3
[Chroma Server] Retrying in 1s...
[Chroma Server] POST /query (attempt 2/3)
[Chroma Server] Server error 500 on attempt 2/3
[Chroma Server] Retrying in 2s...
[Chroma Server] POST /query (attempt 3/3)
[Chroma Server] Server error 500 on attempt 3/3
[Chroma Server] ✗ All 3 retry attempts failed
[Chroma Server] Circuit breaker OPEN (threshold reached: 5/5)

CIRCUIT REJECTION:
[Chroma Server] Circuit breaker OPEN - rejecting request

RECOVERY (HALF_OPEN → CLOSED):
[Chroma Server] Circuit breaker entering HALF_OPEN state
[Chroma Server] GET /health (attempt 1/3)
[Chroma Server] ✓ GET /health succeeded
[Chroma Server] Circuit breaker CLOSED (service recovered)
```

## Scalability & Performance

### Request Throughput with Resilience

```
Without Resilience (Service Down):
  All requests fail immediately
  Load on backend: 100%
  Load on downed service: Heavy (hammering)
  Recovery time: Unknown (service stays down)

With Resilience (Service Down):
  Requests use fallback/cached results
  Load on backend: 10% (circuit rejects early)
  Load on downed service: None (circuit open)
  Recovery time: Automatic (HALF_OPEN testing)
```

### Connection Pool Savings

```
Without Resilience:
  Connection #1 → Timeout (30s default)
  Connection #2 → Timeout (30s default)
  Connection #3 → Timeout (30s default)
  Total connections held: 3 × 30s = 90s waste

With Resilience:
  Connection #1 → Retry in 1s
  Connection #2 → Retry in 2s
  Connection #3 → Fail in 4s (circuit open)
  Total time: 7s (exponential backoff saves resources)
```

## Configuration Reference

| Service | Max Retries | Timeout | Threshold | Recovery |
|---------|-------------|---------|-----------|----------|
| Chroma | 3 | 15s | 5 | 60s |
| Filesystem | 3 | 20s | 5 | 60s |
| Billing | 2 | 5s | 10 | 30s |
| Git | 3 | 30s | 5 | 90s |

---

**See Also**: 
- `SERVICE_RESILIENCE_GUIDE.md` - Detailed configuration guide
- `SERVICE_RESILIENCE_EXAMPLES.md` - Code examples
- `SERVICE_RESILIENCE_SUMMARY.md` - Implementation summary
