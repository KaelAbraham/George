# Production Deployment Guide

## Debug Mode Security

All microservices have been hardened to prevent debug mode from running in production.

### Development vs Production

#### Development Mode (Local)

- **How it runs**: `python app.py` (via `app.run()`)
- **Debug enabled**: YES
- **Hot reload**: YES
- **Gunicorn**: NO
- **When used**: Local development only
- **Condition**: `FLASK_ENV=development`

```bash
# Local development
FLASK_ENV=development python backend/app.py
```

#### Production Mode (Docker)

- **How it runs**: `gunicorn -w 4 -b 0.0.0.0:PORT app:app`
- **Debug enabled**: NO
- **Hot reload**: NO
- **Gunicorn**: YES (4 workers)
- **When used**: Production deployments
- **Condition**: NOT `FLASK_ENV=development`

### Application Code Structure

All Flask applications follow this pattern:

```python
if __name__ == '__main__':
    import os
    if os.getenv('FLASK_ENV') == 'development':
        # Local dev only - app.run() with debug=True
        app.run(debug=True, port=PORT)
    else:
        # Production - use gunicorn
        print("Use gunicorn for production: gunicorn -w 4 -b 0.0.0.0:PORT app:app")
```

This ensures that:
1. `app.run()` is NEVER executed in production
2. Production deployments use gunicorn by default
3. Debug mode cannot be accidentally enabled in production

### Docker Build and Run

#### Dockerfile Structure

All service Dockerfiles follow this pattern:

```dockerfile
FROM python:3.11

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . /app

EXPOSE 6xxx

# Production command - gunicorn, not app.run()
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:6xxx", "app:app"]
```

Key points:
- `gunicorn` is installed as part of requirements
- `CMD` uses `gunicorn`, not `python app.py`
- `FLASK_ENV` is NOT set in Dockerfile (defaults to production)

#### Docker Compose Configurations

**docker-compose.dev.yml** (Development)
```yaml
backend:
  command: flask --app app.py run --host=0.0.0.0 --port=5000 --reload
  environment:
    - FLASK_ENV=development
```

**docker-compose.prod.yml** (Production)
```yaml
backend:
  image: gcr.io/george-ai/backend:latest
  environment:
    - FLASK_ENV=production
```

The production compose uses the Dockerfile `CMD` (gunicorn) automatically.

### Port Allocation Strategy

- **5000-5173**: User-facing services
  - Frontend: 5173
  - Backend API: 5000
- **6000-6099**: Internal microservices (gunicorn)
  - Auth Server: 6001
  - Filesystem Server: 6002
  - Chroma Server: 6003
  - Billing Server: 6004
  - Git Server: 6005
  - External Data Server: 6006
- **7000-7999**: Data stores
  - Neo4j: 7687

### Deployment Checklist

Before deploying to production:

- [ ] `FLASK_ENV=production` is set in deployment manifest
- [ ] No `DEV_MODE=true` flag in production
- [ ] All `*_SERVER_URL` variables point to internal IPs/DNS
- [ ] `INTERNAL_SERVICE_TOKEN` is configured and secure
- [ ] Health check endpoints (`/health`, `/ready`) are responding
- [ ] No debug logs in application output
- [ ] Gunicorn workers are running (check process list)
- [ ] Log aggregation is configured for gunicorn output

### Troubleshooting

#### Service still running in debug mode

**Symptom**: Seeing `Running on http://0.0.0.0:6001` messages or Flask reloader active

**Fix**:
1. Check `FLASK_ENV` environment variable: `echo $FLASK_ENV`
2. Verify Dockerfile CMD: should be `gunicorn ...`, not `python app.py`
3. Verify docker-compose command: should NOT override CMD with `python app.py`
4. Restart container: `docker restart <container>`

#### Gunicorn not found

**Symptom**: Error like `gunicorn: command not found`

**Fix**:
1. Verify Dockerfile installs gunicorn: `RUN pip install ... gunicorn`
2. Rebuild image: `docker build -t service .`
3. Check requirements.txt includes gunicorn

#### Health checks failing

**Symptom**: Service marked as unhealthy

**Fix**:
1. Verify service is accepting connections: `curl http://localhost:6001/health`
2. Check service logs for errors
3. Increase health check timeout if service is slow to start

### Security Implications

**Why remove debug mode from production?**

1. **Code Execution Vulnerability**: Flask debug mode includes an interactive debugger that can execute arbitrary Python code
2. **Sensitive Data Exposure**: Debug mode exposes stack traces with environment variables and secrets
3. **Performance**: Debug mode with auto-reloader is much slower than gunicorn
4. **Best Practices**: WSGI applications (gunicorn) are the standard for production Python web services

### References

- [Flask Deployment Documentation](https://flask.palletsprojects.com/en/latest/deploying/)
- [Gunicorn Documentation](https://gunicorn.org/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [OWASP Flask Security](https://owasp.org/www-community/attacks/Debugging_code)
