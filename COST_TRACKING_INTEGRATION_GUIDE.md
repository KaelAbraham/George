# Cost Tracking Integration Guide

**For:** Backend Developers & Billing Server Maintainers  
**Date:** 2024-01-15  
**Reference:** Commit 3001e57

---

## Quick Summary

The cost tracking fix eliminates the race condition where users receive answers without being charged. It uses a **pre-authorization pattern** with three atomic operations:

1. **Reserve** funds before expensive operation
2. **Capture** actual cost on success OR **Release** on failure
3. Automatic retry with idempotency keys

---

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Backend (app.py)                         │
│                                                             │
│  POST /chat                                                │
│  ├─ [1] reserve_funds($0.05, "user-123")                   │
│  │       ↓ Billing Server                                 │
│  │       ← "res-456"                                      │
│  │                                                         │
│  ├─ [2] Try: model.chat(prompt)                           │
│  │       ├─ Success                                       │
│  │       │  └─ [3a] capture_funds("res-456", $0.04)      │
│  │       │          ↓ Billing Server                     │
│  │       │          ← "captured"                         │
│  │       │                                               │
│  │       └─ Failure                                      │
│  │          └─ [3b] release_funds("res-456")            │
│  │                  ↓ Billing Server                    │
│  │                  ← "released"                        │
│  │                                                       │
│  └─ Return response to user                             │
│                                                         │
└─────────────────────────────────────────────────────────────┘
```

### State Machine

```
Frontend Request
    ↓
╔════════════════════════════════╗
║ CHECK PREREQUISITES            ║
║ - User authenticated           ║
║ - Permission granted           ║
║ - Triage completed             ║
╚════════════════════════════════╝
    ↓
╔════════════════════════════════╗
║ [1] PRE-AUTHORIZE              ║
║ reserve_funds($0.05)           ║
║ Status: ACTIVE                 ║
╚════════════════════════════════╝
    ↓
┌─────────────────────────────────┐
│ TRY: Expensive Operation        │
│ (LLM Call)                      │
└─────────────────────────────────┘
    ↓
    ├─ SUCCESS ─────────────────┐
    │                           ↓
    │               ╔═══════════════════════╗
    │               ║ [3A] CAPTURE          ║
    │               ║ capture_funds(0.04)   ║
    │               ║ Status: CAPTURED      ║
    │               ╚═══════════════════════╝
    │                           ↓
    │               Return Response to User
    │
    └─ FAILURE ────────────────┐
                               ↓
                   ╔═══════════════════════╗
                   ║ [3B] RELEASE          ║
                   ║ release_funds()       ║
                   ║ Status: RELEASED      ║
                   ╚═══════════════════════╝
                               ↓
                   Return Error to User
```

---

## Backend Implementation (app.py)

### Initialization

```python
from cost_tracking import CostTracker
from service_utils import get_internal_headers

# In __init__ section:
cost_tracker = CostTracker(
    billing_server_url=BILLING_SERVER_URL,      # http://localhost:6004
    internal_headers=get_internal_headers()     # Contains X-INTERNAL-TOKEN
)
```

### Chat Endpoint Usage

```python
@blp_chat.route('/chat')
class Chat(MethodView):
    def post(self, data):
        user_id = auth_data['user_id']
        user_query = data['query']
        
        # ... Triage, RAG, etc ...
        
        # STEP 1: PRE-AUTHORIZE
        estimated_cost = 0.05  # GPT-4-like estimate
        reservation_id = cost_tracker.reserve_funds(user_id, estimated_cost)
        
        if not reservation_id:
            # Pre-authorization failed (insufficient balance)
            abort(402, message="Insufficient balance to complete this request.")
        
        # STEP 2: Expensive operation with try/except
        try:
            result_dict = model_to_use.chat(main_prompt, history=history_list)
            draft_answer = result_dict['response']
            call_cost = result_dict.get('cost', 0.0)
            
            # STEP 3A: CAPTURE actual cost
            if reservation_id and call_cost > 0:
                success = cost_tracker.capture_funds(reservation_id, call_cost)
                if not success:
                    # Capture failed - critical billing error
                    # User already got the answer, don't fail response
                    logging.error(f"[CRITICAL] Capture failed for {user_id}: "
                                f"Answer delivered but not charged (reservation: {reservation_id})")
                    # This error should trigger manual investigation
            
            elif reservation_id and call_cost == 0:
                # No charge, release the hold
                cost_tracker.release_funds(reservation_id)
            
            # Success response
            return {
                "message_id": message_id,
                "response": final_answer,
                "cost": call_cost,
                "reservation_id": reservation_id
            }
        
        except Exception as e:
            # STEP 3B: RELEASE on failure
            if reservation_id:
                success = cost_tracker.release_funds(reservation_id)
                if not success:
                    logging.warning(f"[WARNING] Release failed for {user_id}: "
                                  f"Reservation {reservation_id} may be stuck")
            
            # Return error to user
            raise
```

---

## Billing Server Implementation

### Endpoint 1: POST /reserve

**Purpose:** Pre-authorize and hold funds

**Request:**
```json
{
  "user_id": "user-123",
  "reservation_id": "res-456abc",
  "estimated_cost": 0.05
}
```

**Response (200 - Success):**
```json
{
  "reservation_id": "res-456abc",
  "amount_reserved": 0.05,
  "expires_at": "2024-01-15T10:30:00Z"
}
```

**Response (402 - Insufficient Funds):**
```json
{
  "error": "Insufficient balance",
  "available_balance": 0.02,
  "requested_amount": 0.05
}
```

**Implementation Notes:**
- Check user balance >= estimated_cost
- Create reservation record (status: ACTIVE)
- Temporarily hold funds (deduct from available, not confirmed balance)
- Store in DB with expiration (30 minutes)
- Return reservation_id to caller

```python
@billing_app.route('/reserve', methods=['POST'])
def reserve():
    data = request.json
    user_id = data['user_id']
    reservation_id = data['reservation_id']
    estimated_cost = data['estimated_cost']
    
    # Check balance
    user = User.get(user_id)
    if not user or user.balance < estimated_cost:
        return {
            "error": "Insufficient balance",
            "available_balance": user.balance if user else 0
        }, 402
    
    # Create reservation
    reservation = Reservation(
        reservation_id=reservation_id,
        user_id=user_id,
        estimated_cost=estimated_cost,
        status='ACTIVE',
        expires_at=datetime.now() + timedelta(minutes=30)
    )
    db.session.add(reservation)
    
    # Hold funds (don't charge yet)
    user.held_balance += estimated_cost
    user.available_balance -= estimated_cost
    db.session.commit()
    
    return {
        "reservation_id": reservation_id,
        "amount_reserved": estimated_cost,
        "expires_at": reservation.expires_at.isoformat()
    }, 200
```

### Endpoint 2: POST /capture

**Purpose:** Convert hold into real charge (charge actual cost)

**Request:**
```json
{
  "reservation_id": "res-456abc",
  "actual_cost": 0.04
}
```

**Response (200 - Success):**
```json
{
  "status": "captured",
  "amount_charged": 0.04,
  "reservation_id": "res-456abc"
}
```

**Response (409 - Already Captured):**
```json
{
  "error": "Already captured (idempotent)",
  "amount_charged": 0.04,
  "reservation_id": "res-456abc"
}
```

**Implementation Notes:**
- Look up reservation by ID
- If already captured, return 409 (idempotent - treat as success)
- If not found or released, return 404
- Update held_balance: subtract estimated, add back (estimated - actual)
- Create transaction record
- Mark reservation as CAPTURED

```python
@billing_app.route('/capture', methods=['POST'])
def capture():
    data = request.json
    reservation_id = data['reservation_id']
    actual_cost = data['actual_cost']
    
    reservation = Reservation.get(reservation_id)
    
    # Idempotent check
    if not reservation:
        return {"error": "Reservation not found"}, 404
    
    if reservation.status == 'CAPTURED':
        # Already captured - return 409 with charged amount
        return {
            "error": "Already captured (idempotent)",
            "amount_charged": reservation.actual_cost,
            "reservation_id": reservation_id
        }, 409
    
    if reservation.status != 'ACTIVE':
        return {"error": f"Reservation in state {reservation.status}"}, 409
    
    # Update balances
    user = User.get(reservation.user_id)
    
    # Release hold
    user.held_balance -= reservation.estimated_cost
    
    # Charge actual cost
    refund = reservation.estimated_cost - actual_cost
    user.held_balance += refund
    user.available_balance += refund
    
    # Create transaction
    transaction = Transaction(
        user_id=user.user_id,
        reservation_id=reservation_id,
        amount=actual_cost,
        type='CHARGE',
        status='SUCCESS'
    )
    
    # Update reservation
    reservation.status = 'CAPTURED'
    reservation.actual_cost = actual_cost
    
    db.session.add(transaction)
    db.session.commit()
    
    return {
        "status": "captured",
        "amount_charged": actual_cost,
        "refund_amount": refund,
        "reservation_id": reservation_id
    }, 200
```

### Endpoint 3: POST /release

**Purpose:** Release hold and refund reserved funds (on failure)

**Request:**
```json
{
  "reservation_id": "res-456abc"
}
```

**Response (200 - Success):**
```json
{
  "status": "released",
  "amount_refunded": 0.05,
  "reservation_id": "res-456abc"
}
```

**Response (404 - Already Released):**
```json
{
  "error": "Already released (idempotent)",
  "amount_refunded": 0.05,
  "reservation_id": "res-456abc"
}
```

**Implementation Notes:**
- Look up reservation by ID
- If already released, return 404 (idempotent)
- Return held funds to available balance
- Mark reservation as RELEASED
- Create refund transaction

```python
@billing_app.route('/release', methods=['POST'])
def release():
    data = request.json
    reservation_id = data['reservation_id']
    
    reservation = Reservation.get(reservation_id)
    
    if not reservation:
        return {"error": "Reservation not found"}, 404
    
    if reservation.status == 'RELEASED':
        # Already released - idempotent success
        return {
            "error": "Already released (idempotent)",
            "amount_refunded": reservation.estimated_cost,
            "reservation_id": reservation_id
        }, 404
    
    if reservation.status not in ['ACTIVE', 'EXPIRED']:
        return {"error": f"Cannot release from state {reservation.status}"}, 409
    
    # Return funds
    user = User.get(reservation.user_id)
    user.held_balance -= reservation.estimated_cost
    user.available_balance += reservation.estimated_cost
    
    # Create refund transaction
    transaction = Transaction(
        user_id=user.user_id,
        reservation_id=reservation_id,
        amount=reservation.estimated_cost,
        type='REFUND',
        status='SUCCESS'
    )
    
    # Update reservation
    reservation.status = 'RELEASED'
    
    db.session.add(transaction)
    db.session.commit()
    
    return {
        "status": "released",
        "amount_refunded": reservation.estimated_cost,
        "reservation_id": reservation_id
    }, 200
```

### Endpoint 4: POST /deduct (Legacy - Idempotent)

**Purpose:** Legacy single-shot deduction with idempotency key

**Request:**
```json
{
  "user_id": "user-123",
  "job_id": "chat-789xyz",
  "cost": 0.05,
  "description": "Chat: complex_analysis"
}
```

**Response (200 - Success):**
```json
{
  "status": "deducted",
  "amount_charged": 0.05,
  "job_id": "chat-789xyz"
}
```

**Response (409 - Already Deducted):**
```json
{
  "error": "Already deducted (idempotent)",
  "amount_charged": 0.05,
  "job_id": "chat-789xyz"
}
```

**Implementation Notes:**
- Check processed_jobs table for job_id
- If found, return 409 (idempotent - treat as success)
- Otherwise, deduct from balance and record job_id

```python
@billing_app.route('/deduct', methods=['POST'])
def deduct():
    data = request.json
    user_id = data['user_id']
    job_id = data['job_id']
    cost = data['cost']
    description = data['description']
    
    # Idempotency check
    processed_job = ProcessedJob.get(job_id)
    if processed_job:
        return {
            "error": "Already deducted (idempotent)",
            "amount_charged": processed_job.cost,
            "job_id": job_id
        }, 409
    
    # Charge user
    user = User.get(user_id)
    if not user or user.balance < cost:
        return {"error": "Insufficient balance"}, 402
    
    user.balance -= cost
    
    # Record transaction
    transaction = Transaction(
        user_id=user_id,
        job_id=job_id,
        amount=cost,
        description=description,
        type='CHARGE',
        status='SUCCESS'
    )
    
    # Record as processed
    processed_job = ProcessedJob(
        job_id=job_id,
        user_id=user_id,
        cost=cost
    )
    
    db.session.add(transaction)
    db.session.add(processed_job)
    db.session.commit()
    
    return {
        "status": "deducted",
        "amount_charged": cost,
        "job_id": job_id
    }, 200
```

---

## Database Schema

### Reservations Table

```sql
CREATE TABLE reservations (
    reservation_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    estimated_cost DECIMAL(10, 6) NOT NULL,
    actual_cost DECIMAL(10, 6),
    status VARCHAR(50) NOT NULL,  -- ACTIVE, CAPTURED, RELEASED, EXPIRED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    INDEX idx_user_status (user_id, status),
    INDEX idx_expires (expires_at)
);
```

### Processed Jobs Table (for idempotency)

```sql
CREATE TABLE processed_jobs (
    job_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    cost DECIMAL(10, 6) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    INDEX idx_user_job (user_id, job_id)
);
```

### Updated Users Table

```sql
ALTER TABLE users ADD COLUMN held_balance DECIMAL(10, 6) DEFAULT 0;
-- held_balance: funds reserved but not yet charged
-- available_balance = total_balance - held_balance
```

---

## Error Handling Guide

### In Backend (app.py)

| Scenario | Handler | User Experience |
|----------|---------|-----------------|
| Pre-auth fails (funds) | `abort(402)` | "Insufficient balance" - chat never attempted |
| Pre-auth fails (service) | `abort(503)` | "Service temporarily unavailable" - retry later |
| LLM call fails | `except` block → `release()` | "Unable to process your query" - no charge |
| Capture fails | `logging.error()` | Chat response returned anyway - manual review needed |
| Release fails | `logging.warning()` | Error returned - funds still held (expires 30 min) |

### In Billing Server

| Scenario | Response | Notes |
|----------|----------|-------|
| Reserve with low balance | `402` | Prevents unnecessary holds |
| Capture non-existent res | `404` | Return error |
| Capture already captured | `409` | Treat as success (idempotent) |
| Release already released | `404` | Treat as failure but idempotent |
| Job already deducted | `409` | Treat as success (idempotent) |

---

## Monitoring & Observability

### Logging Format

```python
# In backend/app.py
[PREAUTH] Reserving $0.05 for user user-123
[PREAUTH] ✓ Reservation res-456 created successfully

[CAPTURE] Capturing $0.04 for reservation res-456
[CAPTURE] ✓ Captured $0.04

[RELEASE] Releasing reservation res-456
[RELEASE] ✓ Funds released

[CRITICAL] Capture failed for user-123: answer delivered but not charged (reservation: res-456)
```

### Key Metrics

```
# Reservation creation rate
metric: reservations_created_total (gauge)
       {user_id, model, estimated_cost_range}

# Capture success rate
metric: captures_successful_total / captures_attempted_total
       Should be > 99%

# Release rate
metric: releases_total (indicates LLM failure rate)

# Critical failures (answer without charge)
metric: capture_failures_total (should be ~0)
        Alert immediately if > 0
```

### Alerting

```yaml
# Alert on capture failures
alert:
  name: BillingCaptureFailure
  condition: capture_failures_total > 0
  severity: CRITICAL
  message: "User received answer but wasn't charged. Manual investigation required."

# Alert on slow releases
alert:
  name: HighLLMFailureRate
  condition: (releases_total / captures_total) > 0.1
  severity: WARNING
  message: "LLM failure rate unusually high. Check service health."
```

---

## Testing Checklist

- [ ] Test successful reserve → capture flow
- [ ] Test reserve → release on LLM failure
- [ ] Test insufficient balance (pre-auth fails)
- [ ] Test capture idempotency (duplicate request)
- [ ] Test release idempotency
- [ ] Test reservation expiration (after 30 min)
- [ ] Test billing server timeout during capture
- [ ] Test concurrent reservations for same user
- [ ] Test stress (100+ concurrent chats)

---

## Deployment Steps

1. **Deploy Billing Server Changes**
   - Add /reserve, /capture, /release endpoints
   - Add reservations and processed_jobs tables
   - Add held_balance column to users

2. **Deploy Backend Changes**
   - Deploy cost_tracking.py
   - Update app.py with pre-authorization logic
   - Verify CostTracker initialization

3. **Test Integration**
   - Manual test: successful chat flow
   - Manual test: insufficient balance
   - Monitor logs for [PREAUTH], [CAPTURE], [RELEASE]

4. **Enable Monitoring**
   - Set up alerts for capture failures
   - Track success rates

5. **Gradual Rollout**
   - 10% of users for 1 hour
   - Monitor error rates
   - Expand to 50%, then 100%

---

## Rollback Plan

If critical issues arise:

1. Revert backend to old deduct_cost() pattern
2. Keep billing server endpoints (backward compatible)
3. Investigate issue
4. Fix and redeploy

---

**Status:** Ready for integration  
**Maintainer:** Billing Team  
**Last Updated:** 2024-01-15
