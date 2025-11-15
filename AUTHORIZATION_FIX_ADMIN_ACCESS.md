# Authorization Fix: Admin-to-Admin Access Control

## Critical Security Flaw Fixed

### The Vulnerability

**Location**: `backend/app.py`, `_check_project_access()` function (line ~1547)

**The Flaw**:
```python
# BEFORE (VULNERABLE):
def _check_project_access(auth_data: Dict, project_id: str) -> bool:
    if auth_data.get('role') == 'admin':
        return True  # ← ANY admin could access ANY project!
```

**Impact**: 
- **Broken User Isolation**: Any user with the `admin` role could access ANY other admin's projects and files
- **Severity**: CRITICAL - Complete breach of multi-tenant data isolation
- **Scope**: Affects all project-based endpoints in backend (`/chat`, `/proxy/filesystem`, etc.)

**Attack Scenario**:
1. Admin A registers with their Firebase account → becomes admin user
2. Admin B registers separately → becomes admin user with their own projects
3. Admin A discovers Admin B's project_id (e.g., via API exploration or error messages)
4. Admin A calls `/chat` with project_id belonging to Admin B
5. Backend checks `_check_project_access()`: "You're an admin? Cool, access granted!"
6. Admin A can now read, query, and interact with Admin B's private data

---

## The Fix

### Architecture Changes

**1. New Auth Server Endpoint** (`auth_server/app.py`):
```python
@app.route('/internal/projects/<project_id>/check_access', methods=['POST'])
@require_internal_token
def check_user_project_access(project_id):
    """
    INTERNAL-ONLY: Check if a user has access to a project.
    
    Checks BOTH:
    1. Ownership: Is user the admin who created this project?
    2. Guest Access: Has user been explicitly granted permission?
    
    Args (JSON body):
        user_id: The Firebase UID requesting access
        
    Returns:
        {
            "has_access": true/false,
            "access_type": "owner" | "guest" | null,
            "permission_level": "admin" | "read" | "edit" | null
        }
    """
```

**2. Refactored Backend Authorization** (`backend/app.py`):
```python
# AFTER (SECURE):
def _check_project_access(auth_data: Dict, project_id: str) -> bool:
    """
    Check if user has access to a project (owner OR guest).
    
    SECURITY FIX: Queries auth_server to verify actual project ownership.
    - Admins can ONLY access their OWN projects
    - Guests can access projects they've been explicitly granted permission to
    - Role alone is NOT sufficient
    """
    user_id = auth_data.get('user_id')
    
    # Query auth_server for authorization check
    resp = auth_client.post(
        f"/internal/projects/{project_id}/check_access",
        json={'user_id': user_id},
        headers=get_internal_headers()
    )
    
    if resp.status_code == 200:
        data = resp.json()
        return data.get('has_access', False)
    
    # SECURITY: Fail closed - deny access on error
    return False
```

---

## Security Model

### Before (BROKEN)
```
┌─────────────────────────────────────────────┐
│ Backend: _check_project_access()            │
│                                             │
│  if role == 'admin':                        │
│      return True  ← BROKEN!                 │
│                                             │
│  Admin A can access ANY project             │
│  Admin B can access ANY project             │
│  No ownership verification                  │
└─────────────────────────────────────────────┘
```

### After (SECURE)
```
┌─────────────────────────────────────────────┐
│ Backend: _check_project_access()            │
│   ↓ Query auth_server                       │
│   ↓                                          │
│ Auth Server:                                │
│   1. Get project owner from database        │
│   2. Compare: user_id == owner_id?          │
│      ✓ Yes → Owner access granted           │
│      ✗ No  → Check guest permissions        │
│   3. Query guest permissions table          │
│      ✓ Yes → Guest access granted           │
│      ✗ No  → Access denied                  │
│                                             │
│ Admin A can ONLY access Admin A's projects  │
│ Admin B can ONLY access Admin B's projects  │
│ Guests can access projects they're invited  │
└─────────────────────────────────────────────┘
```

---

## Authorization Logic

### Access Control Flow

1. **Owner Check** (Primary):
   ```python
   owner_id = auth_manager.get_project_owner(project_id)
   if owner_id == user_id:
       return {"has_access": True, "access_type": "owner"}
   ```
   - Queries `projects` table: `SELECT owner_id WHERE id = project_id`
   - User is the admin who created the project
   - Full access (admin permission level)

2. **Guest Check** (Secondary):
   ```python
   access_info = auth_manager.check_project_access(user_id, project_id)
   if access_info.get('has_access'):
       return {"has_access": True, "access_type": "guest"}
   ```
   - Queries `project_permissions` table
   - User has been explicitly granted permission by project owner
   - Permission levels: `read`, `comment`, `edit`, `admin`

3. **Deny All Else**:
   ```python
   return {"has_access": False}
   ```
   - User is neither owner nor guest
   - Access denied

### Fail-Safe Mode

**CRITICAL**: Authorization checks **fail closed** on errors.

If auth_server is unreachable:
```python
except ServiceUnavailable:
    # Circuit breaker is open - auth service is down
    logger.error("Auth service down. Failing CLOSED (deny access).")
    return False  # ← Deny access - better safe than sorry
```

**Rationale**:
- **Security > Availability**: Better to deny legitimate requests temporarily than allow unauthorized access
- **Data Protection**: User data is more important than service uptime
- **Audit Trail**: All denied requests are logged for investigation

---

## Testing

### Manual Verification Steps

**Test 1: Admin Cannot Access Other Admin's Project**

1. **Setup**:
   - Register Admin A (email: admin_a@test.com)
   - Register Admin B (email: admin_b@test.com)
   - Admin A creates project: `project_a_123`
   - Admin B creates project: `project_b_456`

2. **Attack Attempt**:
   ```bash
   # Admin A tries to access Admin B's project
   curl -X POST http://localhost:5001/chat \
     -H "Authorization: Bearer <admin_a_token>" \
     -H "Content-Type: application/json" \
     -d '{
       "project_id": "project_b_456",  # ← Admin B's project!
       "query": "What's in this project?"
     }'
   ```

3. **Expected Result**:
   ```json
   {
     "error": "Access denied: You do not have permission to access this project"
   }
   ```
   - Status: 403 Forbidden
   - Logs: `User <admin_a_user_id> denied access to project project_b_456`

4. **Verify Logs**:
   ```bash
   grep "denied access" backend.log
   # Should show Admin A was denied
   ```

**Test 2: Admin CAN Access Own Project**

```bash
# Admin A accesses their own project
curl -X POST http://localhost:5001/chat \
  -H "Authorization: Bearer <admin_a_token>" \
  -d '{"project_id": "project_a_123", "query": "Hello"}'

# Expected: 200 OK, chat response
```

**Test 3: Guest Access Works**

1. **Setup**:
   ```bash
   # Admin A grants guest access to Guest User
   curl -X POST http://localhost:5001/grant_access \
     -H "Authorization: Bearer <admin_a_token>" \
     -d '{
       "project_id": "project_a_123",
       "target_email": "guest@test.com"
     }'
   ```

2. **Verify**:
   ```bash
   # Guest can access project_a_123
   curl -X POST http://localhost:5001/chat \
     -H "Authorization: Bearer <guest_token>" \
     -d '{"project_id": "project_a_123", "query": "Hello"}'
   
   # Expected: 200 OK
   ```

3. **Verify Boundary**:
   ```bash
   # Guest CANNOT access project_b_456 (not granted)
   curl -X POST http://localhost:5001/chat \
     -H "Authorization: Bearer <guest_token>" \
     -d '{"project_id": "project_b_456", "query": "Hello"}'
   
   # Expected: 403 Forbidden
   ```

**Test 4: Fail-Closed Behavior**

1. **Stop auth_server**:
   ```bash
   # Kill auth_server process
   pkill -f "auth_server"
   ```

2. **Attempt Access**:
   ```bash
   curl -X POST http://localhost:5001/chat \
     -H "Authorization: Bearer <admin_a_token>" \
     -d '{"project_id": "project_a_123", "query": "Hello"}'
   ```

3. **Expected Result**:
   ```json
   {"error": "Access denied: You do not have permission to access this project"}
   ```
   - Status: 403 Forbidden
   - Logs: `Auth service is down (circuit breaker open). Failing CLOSED.`

4. **Verify Fail-Safe**:
   - Even legitimate requests are denied when auth_server is down
   - This prevents bypassing authorization checks
   - Service recovers automatically when auth_server comes back up

---

## Database Schema

### Projects Table (auth_server)
```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,           -- project_id
    owner_id TEXT NOT NULL,        -- Firebase UID of owner
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(user_id)
);

CREATE INDEX idx_projects_owner ON projects(owner_id);
```

### Project Permissions Table (auth_server)
```sql
CREATE TABLE project_permissions (
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    permission_level TEXT NOT NULL,  -- 'read', 'edit', 'admin'
    granted_by TEXT,                 -- Who granted this permission
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, user_id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX idx_project_permissions_user ON project_permissions(user_id);
```

---

## Impact Assessment

### Affected Endpoints

**All project-scoped endpoints in `backend/app.py`**:

1. **`POST /chat`** (line ~715)
   - **Before**: Any admin could query any project's knowledge base
   - **After**: Admins can only query their own projects

2. **`POST /proxy/filesystem/...`** (line ~1065)
   - **Before**: Any admin could proxy requests to any project's filesystem
   - **After**: Admins can only access their own project files

3. **Any future project endpoints**:
   - All use `_check_project_access()` for authorization
   - Automatically inherit secure authorization logic

### Migration Notes

**Existing Deployments**:
- **No database migration required** - schema already exists
- **No user action required** - fix is transparent
- **Backward compatible** - guest access still works

**API Contract**:
- **No breaking changes** - all public APIs unchanged
- **Error responses unchanged** - still return 403 on denial
- **New internal endpoint** - `/internal/projects/<id>/check_access` (internal only)

---

## Monitoring & Alerting

### Key Metrics to Track

1. **Authorization Denials**:
   ```bash
   grep "denied access to project" backend.log | wc -l
   ```
   - Spike could indicate attack or misconfiguration

2. **Auth Server Failures**:
   ```bash
   grep "Auth service is down" backend.log | wc -l
   ```
   - Circuit breaker opens when auth_server unavailable
   - Should be rare in healthy system

3. **Unexpected Access Patterns**:
   ```bash
   grep "access_type.*owner" backend.log | sort | uniq -c
   ```
   - Verify admins only access their own projects

### Alert Rules

```yaml
# Example Prometheus alert
- alert: UnauthorizedAccessAttempts
  expr: rate(authorization_denials[5m]) > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High rate of authorization denials detected"

- alert: AuthServerCircuitOpen
  expr: auth_server_circuit_breaker_state == "open"
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Auth server circuit breaker is open"
```

---

## Related Security Fixes

This fix is part of a comprehensive security audit:

1. ✅ **Registration Resilience** (`REGISTRATION_RESILIENCE_FIX.md`)
   - Fixed zombie user problem during billing_server downtime

2. ✅ **Role Escalation** (Previous fix)
   - Fixed role spoofing via X-User-ID header

3. ✅ **Cost Tracking Race Conditions** (Previous fix)
   - Fixed concurrent billing transaction issues

4. ✅ **Authorization Bypass** (This fix)
   - Fixed admin-to-admin access control

5. ⏳ **CSRF Protection** (Already implemented)
   - Rate limiting on sensitive endpoints
   - SameSite cookie policy

---

## Summary

**What Changed**:
- Backend now queries auth_server to verify project ownership
- Admins can ONLY access their own projects
- Guest access still works via explicit permission grants
- Authorization fails closed on errors

**Security Impact**:
- **Eliminates**: Admin-to-admin data access vulnerability
- **Preserves**: Multi-tenant data isolation
- **Improves**: Audit trail for access denials

**User Impact**:
- **Transparent**: No user-facing changes
- **Secure**: Data isolation now enforced correctly
- **Reliable**: Fail-closed prevents security bypass

**Status**: ✅ **IMPLEMENTED AND READY FOR COMMIT**
