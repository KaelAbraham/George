# X-User-ID Header Vulnerability - Security Fix Report

**Date**: November 15, 2025  
**Severity**: 🔴 CRITICAL - Cross-User File Access  
**Status**: ✅ FIXED  

## Vulnerability Summary

The filesystem_server was accepting the `X-User-ID` header from clients without validating that the request came from an authenticated internal service. This allowed an attacker to spoof user IDs and access/modify other users' files.

### Attack Scenario

```python
# Attacker's malicious request
curl -H "X-User-ID: victim-user-123" \
     http://filesystem-server:6002/file/project-456/document.md

# Result: Attacker could read/write victim's files!
```

**Why This Is Critical:**
- Cross-user file access (data breach)
- File modification/deletion (data integrity)
- No audit trail (attacker's actions attributed to victim)
- Affects all user-isolated operations

## Root Cause Analysis

### The Problem

**filesystem_server/app.py** (BEFORE FIX):
```python
@app.before_request
def extract_user_id():
    """Extract X-User-ID from request headers - NO VALIDATION"""
    user_id = request.headers.get('X-User-ID')
    if user_id:
        g.user_id = user_id  # ❌ TRUSTS CLIENT HEADER!
    else:
        g.user_id = 'default'
```

**The Issue:**
1. Any client (authenticated or not) could set `X-User-ID` to any value
2. No verification that the header came from backend
3. Direct file path construction used this untrusted value
4. Result: Complete user isolation bypass

### Why It Happened

The middleware was designed assuming only trusted backend services would call it. However:
1. No token validation in middleware (only on one endpoint via decorator)
2. Some backend endpoints didn't send the internal token
3. Anyone with network access could call filesystem_server directly
4. No assumption that external actors could reach filesystem_server

## The Fix

### Solution Architecture

```
┌────────────────┐
│  User Request  │
└────────┬───────┘
         │
         ▼
┌───────────────────────────────┐
│ Backend (Authenticated)        │
│                               │
│ 1. Verify auth token          │
│ 2. Extract user_id from token │
│ 3. Set X-User-ID header       │
│ 4. Add X-INTERNAL-TOKEN       │
└────────┬──────────────────────┘
         │
         │ Trusted Internal Connection
         │ X-User-ID + X-INTERNAL-TOKEN
         │
         ▼
┌───────────────────────────────┐
│ filesystem_server              │
│                               │
│ 1. ✅ Validate X-INTERNAL-TOKEN│
│ 2. ✅ Only if valid, trust    │
│    X-User-ID                  │
│ 3. Build path with validated  │
│    user_id                    │
└───────────────────────────────┘
```

### Implementation

**Step 1: Import INTERNAL_TOKEN**

filesystem_server/app.py:
```python
from service_utils import require_internal_token, INTERNAL_TOKEN  # ✅ Added INTERNAL_TOKEN
```

**Step 2: Secure Middleware**

filesystem_server/app.py:
```python
@app.before_request
def validate_token_and_extract_user_id():
    """
    CRITICAL SECURITY: Validate X-INTERNAL-TOKEN before trusting X-User-ID header.
    """
    
    # Dev mode: if no token configured, allow (for development)
    if not INTERNAL_TOKEN:
        user_id = request.headers.get('X-User-ID', 'default')
        g.user_id = user_id
        return
    
    # Production: token is configured, MUST validate it
    received_token = request.headers.get('X-INTERNAL-TOKEN')
    
    # ✅ Validate token before trusting X-User-ID
    if not received_token or received_token != INTERNAL_TOKEN:
        logger.warning(f"Unauthorized: invalid token from {request.remote_addr}")
        return jsonify({"error": "Unauthorized - invalid internal token"}), 403
    
    # ✅ Only trust X-User-ID if token is valid
    user_id = request.headers.get('X-User-ID', 'default')
    g.user_id = user_id
```

**Step 3: Backend Sends Both Headers**

backend/app.py (File Retrieval):
```python
# Before: ❌ Missing internal token
headers = {'X-User-ID': auth_data.get('user_id', '')}

# After: ✅ Both headers sent
headers = {'X-User-ID': auth_data.get('user_id', '')}
headers.update(get_internal_headers())  # Adds X-INTERNAL-TOKEN
```

backend/app.py (File Upload):
```python
# Before: ❌ Missing internal token
headers = {'X-User-ID': auth_data.get('user_id', '')}

# After: ✅ Both headers sent
headers = {'X-User-ID': auth_data.get('user_id', '')}
headers.update(get_internal_headers())  # Adds X-INTERNAL-TOKEN
```

## Security Properties After Fix

### ✅ What Now Happens

**Attack Attempt:**
```python
# Attacker tries to spoof user ID
curl -H "X-User-ID: victim-user-123" \
     http://filesystem-server:6002/file/project-456/document.md

# Result: 403 Forbidden
# Reason: No X-INTERNAL-TOKEN header, request rejected
```

**Legitimate Request:**
```python
# Backend (authenticated) makes request
headers = {
    'X-User-ID': 'current-user-789',      # ✅ From authenticated user
    'X-INTERNAL-TOKEN': 'secret-token'    # ✅ Proves it came from backend
}
response = requests.get(..., headers=headers)

# Result: 200 OK
# Reason: Valid internal token, X-User-ID is trusted
```

### Trust Chain

```
User → (authenticates) → Backend
                          ↓
                    (verifies token)
                          ↓
                    Sets X-User-ID + X-INTERNAL-TOKEN
                          ↓
                    filesystem_server
                          ↓
                    (validates X-INTERNAL-TOKEN)
                          ↓
                    Trusts X-User-ID ✅
```

## Endpoints Protected

### filesystem_server Endpoints

All endpoints now protected by middleware:

| Endpoint | Auth Required | X-User-ID Trusted | Status |
|----------|--------------|------------------|--------|
| `POST /projects/<id>/upload` | Token + X-User-ID | ✅ After validation | ✅ Secure |
| `GET /file/<id>/<name>` | Token + X-User-ID | ✅ After validation | ✅ Secure |
| `GET /projects/<id>` | Token + X-User-ID | ✅ After validation | ✅ Secure |
| `DELETE /file/<id>/<name>` | Token + X-User-ID | ✅ After validation | ✅ Secure |
| `POST /save_file` | Token + X-User-ID | ✅ After validation | ✅ Secure |

### backend Endpoints Sending Secure Headers

| Endpoint | Headers Sent | Status |
|----------|-------------|--------|
| `GET /v1/api/file/<id>/<name>` | X-User-ID + X-INTERNAL-TOKEN | ✅ Fixed |
| `POST /v1/api/project/<id>/upload` | X-User-ID + X-INTERNAL-TOKEN | ✅ Fixed |
| `POST /save_file` | X-User-ID + X-INTERNAL-TOKEN | ✅ Was already correct |
| `POST /wiki/*` | X-User-ID + X-INTERNAL-TOKEN | ✅ Was already correct |

## Development vs Production

### Development Mode

If `INTERNAL_SERVICE_TOKEN` is NOT set in environment:
- Middleware allows all requests (for local testing)
- X-User-ID is extracted but not validated
- Useful for development without full setup

```python
# Dev setup (no token needed)
INTERNAL_SERVICE_TOKEN not set
→ filesystem_server allows requests
```

### Production Mode

If `INTERNAL_SERVICE_TOKEN` IS set in environment:
- Middleware ENFORCES internal token validation
- All requests without valid token rejected (403 Forbidden)
- X-User-ID only trusted after token validation

```python
# Prod setup (token required)
INTERNAL_SERVICE_TOKEN=secret-prod-token
→ All requests require matching token
→ 403 if token missing or invalid
```

## Testing the Fix

### Test 1: Unauthorized Direct Access

```python
# Test: Try to access filesystem_server without internal token
import requests

response = requests.get(
    "http://localhost:6002/file/project-123/file.md",
    headers={"X-User-ID": "attacker-user"}
)

# Expected: 403 Forbidden ✅
assert response.status_code == 403
```

### Test 2: Authorized Access with Token

```python
# Test: Proper backend request with token
response = requests.get(
    "http://localhost:6002/file/project-123/file.md",
    headers={
        "X-User-ID": "legitimate-user",
        "X-INTERNAL-TOKEN": "valid-token-value"
    }
)

# Expected: 200 OK (or 404 if file doesn't exist, but NOT 403) ✅
assert response.status_code in [200, 404]
```

### Test 3: Wrong Token

```python
# Test: Request with invalid token
response = requests.get(
    "http://localhost:6002/file/project-123/file.md",
    headers={
        "X-User-ID": "user-123",
        "X-INTERNAL-TOKEN": "wrong-token"
    }
)

# Expected: 403 Forbidden ✅
assert response.status_code == 403
```

## Affected Components

### Code Changes

| File | Change | Severity |
|------|--------|----------|
| `filesystem_server/app.py` | Enhanced middleware with token validation | CRITICAL |
| `backend/app.py` (line ~440) | Added internal token to file GET | HIGH |
| `backend/app.py` (line ~490) | Added internal token to file upload | HIGH |

### No Changes Needed

| Component | Reason |
|-----------|--------|
| Chroma Server | Uses decorator already |
| Billing Server | Uses decorator already |
| Git Server | Uses decorator already |
| Auth Server | Uses decorator already |

## Deployment Instructions

### 1. Update Code

```bash
# Pull latest changes
git pull origin master

# Verify files are updated
git show HEAD:filesystem_server/app.py | grep "validate_token_and_extract_user_id"
git show HEAD:backend/app.py | grep "get_internal_headers"
```

### 2. Ensure Environment Variable

```bash
# Set in production deployment
export INTERNAL_SERVICE_TOKEN="$(openssl rand -hex 32)"

# Or in docker-compose.yml
environment:
  - INTERNAL_SERVICE_TOKEN=your-secure-token-here
```

### 3. Restart Services

```bash
# Restart filesystem_server and backend
docker-compose restart filesystem_server backend

# Or locally
# Terminal 1: python filesystem_server/app.py
# Terminal 2: python backend/app.py
```

### 4. Verify

```bash
# Test unauthorized access is now blocked
curl -H "X-User-ID: attacker" http://localhost:6002/health
# Expected: 403 Forbidden

# Test authorized access still works
curl -H "X-User-ID: user-123" \
     -H "X-INTERNAL-TOKEN: your-token" \
     http://localhost:6002/health
# Expected: 200 OK
```

## Security Checklist

- ✅ X-INTERNAL-TOKEN imported in filesystem_server
- ✅ Middleware validates token before trusting X-User-ID
- ✅ Development mode (no token) still works
- ✅ Production mode (token set) enforces validation
- ✅ Backend sends token on file GET endpoint
- ✅ Backend sends token on file upload endpoint
- ✅ Backend sends token on save_file endpoint ✅ (was already correct)
- ✅ All responses properly logged
- ✅ 403 error returned for invalid tokens
- ✅ Warning logs for unauthorized attempts

## Related Security Measures

This fix complements:
- ✅ Internal token enforcement on all services
- ✅ Path traversal validation (validate_project_path)
- ✅ Upload size limits (MAX_CONTENT_LENGTH)
- ✅ User isolation (PROJECTS_FOLDER/user_id/project_id)

## Timeline

| Date | Event |
|------|-------|
| 2025-11-15 | Vulnerability identified |
| 2025-11-15 | Fix implemented |
| 2025-11-15 | Code reviewed |
| 2025-11-15 | Tests created |
| 2025-11-15 | Documentation written |
| 2025-11-15 | Ready for deployment |

## References

- **CWE-347**: Improper Verification of Cryptographic Signature
- **CWE-345**: Insufficient Verification of Data Authenticity
- **OWASP**: Authentication Testing
- **Security.txt**: Header Validation Best Practices

## Conclusion

✅ **CRITICAL VULNERABILITY FIXED**

The X-User-ID header is now protected by requiring a valid `X-INTERNAL-TOKEN`. This ensures that only authenticated backend services can set user IDs, preventing cross-user file access attacks.

**Security Status**: 🟢 SECURE

All user file operations are now protected by a validated trust chain:
1. User authenticates with backend
2. Backend verifies auth token
3. Backend sends X-User-ID + X-INTERNAL-TOKEN
4. filesystem_server validates token before trusting X-User-ID
5. Files accessed with correct user isolation

---

**Deploy Immediately**: This is a critical security fix that should be deployed as soon as possible.

**Monitoring**: Watch logs for 403 Forbidden errors on filesystem_server to detect any unauthorized access attempts.
