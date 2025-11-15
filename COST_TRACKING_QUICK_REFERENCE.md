# Cost Tracking Quick Reference

**Quick guide for developers working with cost tracking**

---

## The Problem in 30 Seconds

User calls expensive LLM → gets answer → billing fails → answer without charge ❌

## The Solution in 30 Seconds

```
Reserve funds BEFORE → Do operation → Capture OR Release AFTER
```

If any step fails, automatic rollback. Either both succeed or both fail.

---

## How to Use in Chat Endpoint

### 3-Step Pattern

```python
# STEP 1: Pre-authorize BEFORE expensive operation
reservation_id = cost_tracker.reserve_funds(user_id, estimated_cost=0.05)
if not reservation_id:
    abort(402, "Insufficient balance")

try:
    # STEP 2: Do expensive operation
    result = model.chat(prompt)
    actual_cost = result['cost']
    
    # STEP 3A: Capture on success
    cost_tracker.capture_funds(reservation_id, actual_cost)
    return {"response": result['response'], "cost": actual_cost}

except Exception as e:
    # STEP 3B: Release on failure
    cost_tracker.release_funds(reservation_id)
    raise
```

---

## API Reference

### CostTracker Methods

```python
# PRE-AUTHORIZE: Hold funds before operation
reservation_id = cost_tracker.reserve_funds(
    user_id="user-123",
    estimated_cost=0.05
)
# Returns: "res-456abc" or None (if insufficient funds)

# CAPTURE: Charge actual cost after success
success = cost_tracker.capture_funds(
    reservation_id="res-456abc",
    actual_cost=0.04
)
# Returns: True or False

# RELEASE: Refund on failure
success = cost_tracker.release_funds(
    reservation_id="res-456abc"
)
# Returns: True or False

# LEGACY: Idempotent single-shot (not recommended for chat)
success = cost_tracker.deduct_cost_idempotent(
    user_id="user-123",
    job_id="chat-789xyz",
    cost=0.05,
    description="Chat: complex_analysis"
)
# Returns: True or False
```

---

## Scenarios

### ✅ Success

```
reserve($0.05) → success
  ↓
chat() → returns $0.04
  ↓
capture($0.04) → success
  ↓
User: Got answer ✓
User: Charged $0.04 ✓
```

### ❌ Insufficient Funds

```
reserve($0.05) → returns None (insufficient)
  ↓
abort(402, "Insufficient balance")
  ↓
User: No answer ✗
User: Not charged ✓
```

### ❌ LLM Timeout

```
reserve($0.05) → success
  ↓
chat() → fails (timeout)
  ↓
catch → release($0.05)
  ↓
User: No answer ✗
User: Not charged ✓
```

### ⚠️ Capture Fails (Critical)

```
reserve($0.05) → success
  ↓
chat() → success, returns $0.04
  ↓
capture($0.04) → FAILS
  ↓
logging.error("CRITICAL: Charge failed")
  ↓
User: Got answer ✓
User: NOT charged ✗
  ↓
Manual investigation required
```

---

## Error Codes

| Code | Meaning | What to Do |
|------|---------|-----------|
| 402 | Insufficient balance | Pre-auth failed, abort |
| 503 | Service unavailable | Billing server down, abort |
| 409 | Already processed | Idempotent (treat as success) |
| 404 | Not found | Released already, treat as error |

---

## Logging Examples

```
[PREAUTH] Reserving $0.05 for user-123
[PREAUTH] ✓ Reservation res-456 created successfully
[PREAUTH] ✗ Pre-auth failed for user-123: Insufficient funds

[CAPTURE] Capturing $0.04 for reservation res-456
[CAPTURE] ✓ Captured $0.04
[CAPTURE] ✗ Capture failed: Billing server returned 500

[RELEASE] Releasing reservation res-456
[RELEASE] ✓ Funds released
[RELEASE] ✗ Release failed: Connection timeout

[CRITICAL] Capture failed for user-123: Answer delivered but not charged (res-456)
```

---

## Idempotency

### Pre-Authorization is NOT Idempotent

```
# Don't retry reserve_funds() - it creates duplicate holds!
res_id = cost_tracker.reserve_funds(user_id, 0.05)
res_id = cost_tracker.reserve_funds(user_id, 0.05)  # WRONG!
# Result: $0.10 held instead of $0.05
```

### Capture IS Idempotent

```
# Safe to retry capture_funds() - returns 409 on duplicate
success = cost_tracker.capture_funds(res_id, 0.04)
success = cost_tracker.capture_funds(res_id, 0.04)  # OK - idempotent
# Result: Charged $0.04 (not $0.08)
```

### Release IS Idempotent

```
# Safe to retry release_funds()
success = cost_tracker.release_funds(res_id)
success = cost_tracker.release_funds(res_id)  # OK - idempotent
# Result: Refunded once
```

---

## Common Mistakes

### ❌ Calling reserve() twice
```python
# WRONG
res1 = cost_tracker.reserve_funds(user_id, 0.05)
res2 = cost_tracker.reserve_funds(user_id, 0.05)  # Doubles hold!
```

### ❌ Forgetting to release on error
```python
# WRONG
reservation_id = cost_tracker.reserve_funds(user_id, 0.05)

try:
    result = model.chat(prompt)
except:
    # OOPS - forgot to release!
    raise
```

### ❌ Not checking reserve_funds() return value
```python
# WRONG
reservation_id = cost_tracker.reserve_funds(user_id, 0.05)
result = model.chat(prompt)  # But reserve() might have returned None!
```

### ✅ Correct Pattern
```python
# RIGHT
reservation_id = cost_tracker.reserve_funds(user_id, 0.05)
if not reservation_id:  # Check return value
    abort(402, "Insufficient balance")

try:
    result = model.chat(prompt)
    cost_tracker.capture_funds(reservation_id, result['cost'])
except:
    cost_tracker.release_funds(reservation_id)  # Always release
    raise
```

---

## Testing

### Unit Test

```python
def test_successful_flow():
    res_id = cost_tracker.reserve_funds("user-1", 0.05)
    assert res_id is not None
    
    success = cost_tracker.capture_funds(res_id, 0.04)
    assert success is True
```

### Integration Test

```python
def test_chat_with_preauth():
    response = client.post('/chat', json={
        'query': 'Test',
        'project_id': 'proj-1'
    })
    
    assert response.status_code == 200
    assert 'reservation_id' in response.json()
```

### Error Test

```python
def test_insufficient_funds():
    mock_balance(user_id, 0)  # Set balance to 0
    
    response = client.post('/chat', json={...})
    
    assert response.status_code == 402
```

---

## Troubleshooting

### Reservation Stuck?

```python
# Check pending reservations
pending = cost_tracker.get_pending_reservations(user_id)
for res in pending:
    print(f"Stuck: {res['reservation_id']}")
    # Manually release if > 30 min old
```

### High Capture Failures?

```
Check:
1. Is billing server running?
2. Is network latency high?
3. Are there recent errors in billing logs?
4. Is X-INTERNAL-TOKEN set correctly?
```

### Need to Debug?

```python
# Check reservation history
history = cost_tracker.get_reservation_history("res-456abc")
print(history)
# {
#   'reservation_id': 'res-456abc',
#   'user_id': 'user-123',
#   'estimated_cost': 0.05,
#   'actual_cost': 0.04,
#   'state': 'CAPTURED',
#   'created_at': '2024-01-15T10:00:00',
#   'updated_at': '2024-01-15T10:00:05'
# }
```

---

## Billing Server Expected Responses

### /reserve

```
200 Success:
{
  "reservation_id": "res-456",
  "amount_reserved": 0.05
}

402 Insufficient Funds:
{
  "error": "Insufficient balance",
  "available_balance": 0.02
}
```

### /capture

```
200 Success:
{
  "status": "captured",
  "amount_charged": 0.04
}

409 Already Captured:
{
  "error": "Already captured (idempotent)",
  "amount_charged": 0.04
}
```

### /release

```
200 Success:
{
  "status": "released",
  "amount_refunded": 0.05
}

404 Already Released:
{
  "error": "Already released (idempotent)"
}
```

---

## Key Takeaways

✅ **DO:**
- Call reserve() BEFORE expensive operation
- Check reservation_id return value
- Always release on exception
- Monitor capture failures

❌ **DON'T:**
- Retry reserve() (creates duplicate holds)
- Forget error handling
- Ignore logging errors
- Call capture() without reservation_id

🎯 **Remember:**
- Either user gets answer AND is charged, or neither
- Never both or neither

---

## Documentation Links

- **Full Guide:** COST_TRACKING_RACE_CONDITION_FIX.md
- **Integration:** COST_TRACKING_INTEGRATION_GUIDE.md
- **Source:** backend/cost_tracking.py
- **Chat Integration:** backend/app.py (around line 600)

---

**Last Updated:** 2024-01-15  
**Status:** Ready for use  
**Questions?** Check COST_TRACKING_RACE_CONDITION_FIX.md for details
