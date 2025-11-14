# 🔐 Secure HttpOnly Cookie Authentication

This document describes the complete secure authentication implementation using HttpOnly cookies and the gatekeeper pattern.

## 🏗️ Architecture Overview

### Backend (Flask)
- Acts as the **"Gatekeeper"** - sole entry point for authentication
- Proxies auth requests to Auth Server
- Sets secure HttpOnly cookies on successful login
- Reads tokens from cookies for all subsequent requests
- Never exposes auth details to frontend

### Frontend (React)
- Posts credentials to `/v1/api/auth/login`
- Receives user data in response (token stays in secure cookie)
- Sends cookies automatically with all requests via `withCredentials: true`
- Cannot access the token directly (security feature)

## 🔑 Key Security Features

### HttpOnly Cookies
```
httponly=True   ← Cannot be accessed by JavaScript
secure=True     ← Only sent over HTTPS (production)
samesite=Lax    ← CSRF protection
```

### Gatekeeper Pattern
Only three public auth endpoints:
- `POST /v1/api/auth/login` - Login with email/password
- `POST /v1/api/auth/logout` - Clear session
- `GET /v1/api/auth/check` - Verify current session

All other microservices are **internal-only** and never exposed.

## 📋 Implementation Checklist

### Backend (✅ Complete)
- [x] Add `make_response` import
- [x] Create `/v1/api/auth/login` proxy route
- [x] Create `/v1/api/auth/logout` proxy route  
- [x] Create `/v1/api/auth/check` proxy route
- [x] Update `_get_user_from_request()` to read from cookies

### Frontend (✅ Complete)
- [x] Create `src/api.ts` with `withCredentials: true`
- [x] Create `src/types.ts` with type definitions
- [x] Create `src/contexts/AppContext.tsx` with auth state
- [x] Create `src/components/LoginView.tsx` with login form
- [x] Create `src/App.tsx` with routing and auth guards

## 🚀 Usage

### Frontend Login Flow

```typescript
import { useContext } from 'react';
import { AppContext } from './contexts/AppContext';

function MyComponent() {
  const auth = useContext(AppContext);
  
  const handleLogin = async () => {
    try {
      await auth.login({ email: 'user@example.com', password: 'password' });
      // User is now authenticated
      // Token is in secure HttpOnly cookie
    } catch (error) {
      console.error('Login failed:', error);
    }
  };
  
  return <button onClick={handleLogin}>Login</button>;
}
```

### Checking Authentication

```typescript
function ProtectedComponent() {
  const auth = useContext(AppContext);
  
  if (!auth.isAuthenticated) {
    return <Navigate to="/login" />;
  }
  
  return <div>Welcome, {auth.user?.email}</div>;
}
```

### Making Authenticated API Calls

```typescript
import * as api from './api';

// This automatically includes the secure cookie
const response = await api.sendChat(query, projectId);
```

## 🔄 Data Flow

### Login Sequence
```
1. User enters email/password in LoginView
   ↓
2. Frontend POST /v1/api/auth/login
   ↓
3. Backend proxies to AUTH_SERVER/login
   ↓
4. Auth Server returns token + user data
   ↓
5. Backend sets HttpOnly cookie with token
   ↓
6. Backend returns user data (no token) to frontend
   ↓
7. Frontend updates AppContext
   ↓
8. Router redirects to dashboard
```

### Subsequent Requests Sequence
```
1. Frontend makes API call (e.g., POST /v1/api/chat)
   ↓
2. Axios includes HttpOnly cookie automatically (withCredentials: true)
   ↓
3. Backend reads token from cookie via _get_user_from_request()
   ↓
4. Backend verifies token with AUTH_SERVER
   ↓
5. Backend processes request
   ↓
6. Response sent back to frontend
```

## 🛡️ Security Properties

| Property | Value | Why |
|----------|-------|-----|
| Token Storage | HttpOnly Cookie | JS cannot access it |
| Cookie Access | Server-side only | Browser auto-sends it |
| XSS Protection | HttpOnly flag | Malicious JS can't steal it |
| CSRF Protection | SameSite=Lax | Prevents cross-site forgery |
| HTTPS Only | secure=True (prod) | Man-in-the-middle protection |

## 🚨 Important Notes

### Development vs Production

**Development** (localhost):
```python
response.set_cookie('auth_token', value=token, httponly=True, secure=True, samesite='Lax')
```
The `secure=True` flag allows HTTP on localhost.

**Production** (https://example.com):
```python
response.set_cookie('auth_token', value=token, httponly=True, secure=True, samesite='Strict')
```
Consider using `samesite='Strict'` for additional CSRF protection.

### CORS Configuration

Ensure CORS is properly configured to allow credentials:
```python
from flask_cors import CORS

CORS(app, supports_credentials=True, origins=['http://localhost:5173', 'https://yourdomain.com'])
```

### Token Refresh

For long-lived sessions, implement token refresh:
```python
@app.route('/v1/api/auth/refresh', methods=['POST'])
def refresh_token():
    """Refresh the auth token"""
    # Implementation here
```

## 📚 File Structure

```
backend/
  app.py                    # Auth proxy routes + gatekeeper
  
frontend/src/
  api.ts                    # Axios instance with withCredentials
  types.ts                  # Type definitions
  App.tsx                   # Router setup + auth guards
  contexts/
    AppContext.tsx          # Auth state management
  components/
    LoginView.tsx           # Login form component
```

## 🧪 Testing the Implementation

### 1. Test Login
```bash
curl -X POST http://localhost:5000/v1/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}' \
  -v
```

Look for the `Set-Cookie` header with `auth_token`.

### 2. Test Protected Route
```bash
curl http://localhost:5000/v1/api/auth/check \
  -H "Cookie: auth_token=YOUR_TOKEN" \
  -v
```

### 3. Test with Browser
Visit `http://localhost:5173/login` and observe:
- No `Authorization` header in requests
- Cookie automatically sent with each request
- Token not visible in browser console

## 🐛 Troubleshooting

### Cookie Not Being Set
- Check that backend returns `Set-Cookie` header
- Verify `httponly=True` is set
- In dev, `secure=True` should still work on localhost

### Frontend Not Sending Cookie
- Ensure `withCredentials: true` in axios
- Check CORS headers include `Access-Control-Allow-Credentials: true`

### Token Verification Failing
- Verify cookie is being sent (`Network` tab in DevTools)
- Check auth service is returning valid responses
- Ensure `AUTH_SERVER_URL` is correct

## 📖 Further Reading

- [OWASP: Session Management](https://owasp.org/www-community/attacks/Session_fixation)
- [MDN: HttpOnly Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies)
- [Flask Security](https://flask.palletsprojects.com/en/latest/security/)
- [Axios withCredentials](https://axios-http.com/docs/req_config)
