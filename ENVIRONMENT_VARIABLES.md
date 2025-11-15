# Environment Variables Reference

This document standardizes all environment variables used across the Caudex Pro microservices architecture.

## Port Allocation

The system reserves port ranges for different types of services:

- **5000-5173**: User-facing services (Frontend: 5173, Backend API: 5000)
- **6000-6099**: Internal microservices (Backend to Backend communication)
- **7000-7999**: Data stores and external systems (Neo4j: 7474/7687)

## Internal Service URLs

All internal services use the **6000-series ports** for inter-service communication. This separation ensures:
- Clear distinction between public and internal APIs
- Easier firewall configuration in production
- Consistent naming conventions

### Service URLs and Defaults

| Service | Environment Variable | Docker Default | Local Default | Port |
|---------|----------------------|-----------------|---------------|------|
| Auth Server | `AUTH_SERVER_URL` | `http://auth:6001` | `http://localhost:6001` | 6001 |
| Filesystem Server | `FILESYSTEM_SERVER_URL` | `http://filesystem:6002` | `http://localhost:6002` | 6002 |
| Chroma/Vector DB | `CHROMA_SERVER_URL` | `http://chroma:6003` | `http://localhost:6003` | 6003 |
| Billing Server | `BILLING_SERVER_URL` | `http://billing:6004` | `http://localhost:6004` | 6004 |
| Git Server | `GIT_SERVER_URL` | `http://git:6005` | `http://localhost:6005` | 6005 |
| External Data Server | `EXTERNAL_DATA_SERVER_URL` | `http://external_data:6006` | `http://localhost:6006` | 6006 |
| Neo4j Graph DB | `GRAPH_SERVER_URL` | `bolt://graph_server:7687` | `bolt://localhost:7687` | 7687 |

## Setting Environment Variables

### Docker Compose (Development)

```yaml
environment:
  - AUTH_SERVER_URL=http://auth:6001
  - FILESYSTEM_SERVER_URL=http://filesystem:6002
  - CHROMA_SERVER_URL=http://chroma:6003
  - BILLING_SERVER_URL=http://billing:6004
  - GIT_SERVER_URL=http://git:6005
  - EXTERNAL_DATA_SERVER_URL=http://external_data:6006
  - GRAPH_SERVER_URL=bolt://graph_server:7687
```

### Local Development (.env files)

For local development without Docker, create `.env` files in each service directory:

**backend/.env**
```env
AUTH_SERVER_URL=http://localhost:6001
FILESYSTEM_SERVER_URL=http://localhost:6002
CHROMA_SERVER_URL=http://localhost:6003
BILLING_SERVER_URL=http://localhost:6004
GIT_SERVER_URL=http://localhost:6005
EXTERNAL_DATA_SERVER_URL=http://localhost:6006
GRAPH_SERVER_URL=bolt://localhost:7687
```

**auth_server/.env**
```env
BILLING_SERVER_URL=http://localhost:6004
```

**filesystem_server/.env**
```env
CHROMA_SERVER_URL=http://localhost:6003
```

### Production Deployment

For production deployments on GCP or other cloud platforms, set:

```env
AUTH_SERVER_URL=http://auth-internal:6001          # Internal DNS or private IP
FILESYSTEM_SERVER_URL=http://filesystem-internal:6002
CHROMA_SERVER_URL=http://chroma-internal:6003
BILLING_SERVER_URL=http://billing-internal:6004
GIT_SERVER_URL=http://git-internal:6005
EXTERNAL_DATA_SERVER_URL=http://external-data-internal:6006
GRAPH_SERVER_URL=bolt://graph-server:7687
```

## Critical Environment Variables

### Core Configuration

| Variable | Purpose | Example |
|----------|---------|---------|
| `FLASK_ENV` | Flask mode (development/production) | `development` or `production` |
| `DEV_MODE` | Dev-only features and defaults | `true` or `false` |
| `PYTHONUNBUFFERED` | Unbuffered output to logs | `1` |

### Security

| Variable | Purpose | Example |
|----------|---------|---------|
| `INTERNAL_SERVICE_TOKEN` | Token for inter-service authentication | (generated secure token) |
| `DEV_MOCK_USER_ID` | Mock user ID in development | `dev-mock-user-1` |

### API Keys & Authentication

| Variable | Purpose | Example |
|----------|---------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Firebase admin SDK credentials | `/app/firebase-key.json` |
| `GEMINI_API_KEY` | Google Gemini API key | (API key) |

### Database URLs

| Variable | Purpose | Example |
|----------|---------|---------|
| `GRAPH_SERVER_URL` | Neo4j connection | `bolt://localhost:7687` |

## Validation Checklist

Before deploying, verify:

- [ ] All `*_SERVER_URL` variables are set consistently across services
- [ ] Port numbers match the allocation table above
- [ ] Docker Compose uses internal DNS names (e.g., `http://auth:6001`)
- [ ] Local development uses `localhost` (e.g., `http://localhost:6001`)
- [ ] Production uses appropriate internal IPs or DNS
- [ ] `INTERNAL_SERVICE_TOKEN` is set and consistent across all services
- [ ] `FLASK_ENV=production` is set in production deployments
- [ ] No hardcoded URLs remain in source code (all use `os.environ.get()`)

## Service Discovery Pattern

All services follow this pattern for URL configuration:

```python
# Internal service URLs (6000-series ports are reserved for internal services)
SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:6xxx")
```

This allows:
1. **Override in Docker**: Environment variables override defaults
2. **Local development**: Falls back to localhost
3. **Production flexibility**: Supports any DNS/IP without code changes

## Troubleshooting

### Service Unreachable Errors

1. Verify URL in logs matches expected service
2. Check port number is in 6000-6099 range
3. In Docker: Use service name (e.g., `http://auth:6001`)
4. Locally: Use `http://localhost:6001`
5. Check `INTERNAL_SERVICE_TOKEN` is passed in `X-INTERNAL-TOKEN` header

### Hardcoded URL Issues

Search codebase for:
- `localhost:5xxx` (should be `6xxx` for internal services)
- Literal `http://` strings (should use `os.environ.get()`)

```bash
grep -r "localhost:5[0-9]" --include="*.py"
grep -r "http://.*:5[0-9]" --include="*.py"
```
