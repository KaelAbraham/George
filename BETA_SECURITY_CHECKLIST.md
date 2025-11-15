# Pre-Launch Security Checklist - Beta Deployment

**Status:** ✅ IN PROGRESS
**Last Updated:** November 15, 2025

## Critical Security Fixes

### ✅ 1. Internal Service Token Authentication

**Risk Level:** CRITICAL (was unprotected, now fixed)

- [x] Auth Server → Billing Server calls include token
  - `GET /stats/subscription_count` requires token
  - `POST /account` requires token
- [x] Backend → Billing Server calls include token
  - Pre-auth, capture, release endpoints all use token
- [x] Backend → Filesystem Server calls include token
  - File save, delete operations all use token
- [x] Backend → Git Server calls include token
  - Snapshot operations use token
- [x] Billing Server endpoints protected
  - `/account` - requires `@require_internal_token`
  - `/balance/<user_id>` - requires `@require_internal_token`
  - `/deduct` - requires `@require_internal_token`
  - `/top_up` - requires `@require_internal_token`
- [x] Filesystem Server validates token in middleware
  - Rejects all requests without valid token before trusting `X-User-ID`
- [x] Documentation created: `INTERNAL_TOKEN_SECURITY_FIX.md`
- [ ] **DEPLOY ACTION:** Generate unique `INTERNAL_SERVICE_TOKEN` for production
- [ ] **DEPLOY ACTION:** Set token in all service `.env` files

### ✅ 2. Pre-Authorization Billing (Race Condition Fix)

**Risk Level:** HIGH (prevents "answer without charge" scenario)

- [x] `CostTracker` class implemented with `/reserve` → `/capture` flow
- [x] Backend chat endpoint uses pre-auth before LLM call
- [x] Idempotent transaction support with job IDs
- [x] Automatic rollback on failure
- [x] SQLite persistence for reconciliation
- [ ] **DEPLOY ACTION:** Verify billing server has `/reserve`, `/capture`, `/release` endpoints

### ✅ 3. Cost Tracking & Monitoring

**Risk Level:** MEDIUM

- [x] Cost aggregation across models (Gemini-Flash, Gemini-Pro, etc.)
- [x] Per-user balance tracking
- [x] Cost logging to SQLite
- [x] Monitoring endpoints: `/monitoring/health`, `/monitoring/queue/stats`
- [ ] **DEPLOY ACTION:** Configure monitoring alerts for charge failures

### ⚠️ 4. Known Issues (Not Yet Fixed)

| Issue | Severity | Status | Impact |
|-------|----------|--------|--------|
| Billing server `/reserve`, `/capture`, `/release` endpoints not yet implemented | HIGH | 📋 Pending | Pre-auth flow won't work until endpoints exist |
| No rate limiting on public endpoints | MEDIUM | 📋 Backlog | Vulnerable to abuse/spam |
| No CSRF protection on state-changing endpoints | LOW | 📋 Backlog | Could be exploited via session hijacking |
| Firebase security rules not fully configured | MEDIUM | 📋 Backlog | Potential unauthorized database access |

## Required Before Beta Launch

### Immediate (Before ANY public access)

- [ ] Generate production `INTERNAL_SERVICE_TOKEN`
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- [ ] Set token in all service `.env` files
  - `backend/.env`: `INTERNAL_SERVICE_TOKEN=...`
  - `billing_server/.env`: `INTERNAL_SERVICE_TOKEN=...`
  - `auth_server/.env`: `INTERNAL_SERVICE_TOKEN=...`
  - `filesystem_server/.env`: `INTERNAL_SERVICE_TOKEN=...`
  - `git_server/.env`: `INTERNAL_SERVICE_TOKEN=...`
  - `chroma_server/.env`: `INTERNAL_SERVICE_TOKEN=...`

- [ ] Verify token is NOT in version control
  - Check `.gitignore` includes `*.env`
  - Run `git status` to ensure no `.env` files are staged

- [ ] Implement billing server `/reserve`, `/capture`, `/release` endpoints
  - Reference: `COST_TRACKING_INTEGRATION_GUIDE.md`
  - Test: Pre-auth flow end-to-end

- [ ] Test internal token validation
  - [ ] Unprotected requests without token → 403 Forbidden
  - [ ] Protected requests with valid token → 200 OK
  - [ ] Protected requests with invalid token → 403 Forbidden

### Short-term (Before 100 users)

- [ ] Enable rate limiting on public endpoints
- [ ] Configure backup strategy for billing database
- [ ] Set up monitoring/alerting for:
  - [ ] Failed charge attempts
  - [ ] Repeated 403 authorization failures (attack indicator)
  - [ ] Service unavailability (circuit breaker trips)

### Medium-term (Within 1 month)

- [ ] Implement CSRF protection
- [ ] Configure Firebase security rules fully
- [ ] Set up audit logging for all financial operations
- [ ] Implement request signing (beyond token auth)

## Testing Checklist

### Security Tests

```bash
# Test 1: Unprotected billing request (should fail)
curl -X POST http://localhost:6004/account \
  -H "Content-Type: application/json" \
  -d '{"user_id": "hack-user", "tier": "admin"}'
# Expected: 403 Forbidden

# Test 2: Protected billing request with valid token (should succeed)
curl -X POST http://localhost:6004/account \
  -H "Content-Type: application/json" \
  -H "X-INTERNAL-TOKEN: your-secret-token" \
  -d '{"user_id": "valid-user", "tier": "pro"}'
# Expected: 201 Created

# Test 3: Check token is required from auth server
curl "http://localhost:6001/validate_invite" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"code": "TEST_CODE"}'
# Should verify token is included in downstream call to billing

# Test 4: Filesystem requires token
curl "http://localhost:6002/file/test-project/test.md"
# Expected: 403 Forbidden (no X-INTERNAL-TOKEN)
```

### Functional Tests

- [ ] User registration flow works end-to-end with token
- [ ] Chat endpoint with pre-auth → LLM call → capture flow
- [ ] File upload with internal token validation
- [ ] Wiki generation with distributed saga pattern

## Monitoring & Alerts

### Critical Alerts (Page on-call)

1. **Repeated 403 Unauthorized Errors**
   - Could indicate: Attack attempt, token mismatch, service misconfiguration
   - Action: Check service logs, verify INTERNAL_SERVICE_TOKEN is set correctly

2. **Charge Capture Failures**
   - Could indicate: Billing service down, database locked, insufficient funds
   - Action: Check billing service health, verify database consistency

3. **Circuit Breaker Open**
   - Could indicate: Service cascade failure
   - Action: Investigate which service is failing, may need restart

### Warning Alerts (Notify team)

1. **High error rate on public endpoints**
2. **Cost tracking discrepancies** (amount reserved ≠ amount captured)
3. **Worker process deaths** (job queue stuck)

## Deployment Order

1. **Deploy all services with INTERNAL_SERVICE_TOKEN configured**
   - Ensure all services get the same token
   - Services will fail requests without token (intended behavior)

2. **Verify internal calls work**
   - Test billing endpoint with token header
   - Test filesystem endpoint with token header
   - Check logs for "Authorized request" messages

3. **Monitor for errors**
   - Watch for "Unauthorized internal request" warnings
   - These indicate service misconfiguration

4. **Open to beta testers**
   - Once all internal calls verified, allow users

## Rollback Plan

If token causes widespread issues:

1. Remove `@require_internal_token` decorators from billing endpoints (temporary)
2. Set `INTERNAL_SERVICE_TOKEN=""` (empty) in services
3. Restart services
4. Investigate root cause
5. Re-apply token after fix

## Documentation References

- `INTERNAL_TOKEN_SECURITY_FIX.md` - Detailed security fix
- `COST_TRACKING_INTEGRATION_GUIDE.md` - Billing endpoint implementation
- `ENVIRONMENT_VARIABLES.md` - Configuration reference
- `DEPLOYMENT_GUIDE.md` - Full deployment process

## Sign-Off

| Role | Name | Date | Sign-Off |
|------|------|------|----------|
| Security Lead | — | — | — |
| Backend Lead | — | — | — |
| DevOps Lead | — | — | — |
| Product Manager | — | — | — |

---

**Last Reviewed:** November 15, 2025  
**Next Review:** Before each production deployment  
**Maintained By:** Security Team
