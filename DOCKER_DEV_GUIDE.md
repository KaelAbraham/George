# 🐳 CaudexPro Docker Development Environment

This Docker Compose setup provides a complete development environment for CaudexPro with:

## ✅ Services

### **Frontend** (Port 5173)
- Vite dev server with hot reload
- Auto-rebuilds on file changes
- Runs from `./frontend` directory

### **Backend** (Port 5000) - The "Brain"
- Flask development server with auto-reload
- Public API endpoint: `http://localhost:5000/v1/api`
- Communicates with all microservices

### **Microservices** (Internal Only - Not exposed to outside)
- **auth_server** (port 6001) - Authentication
- **filesystem_server** (port 6002) - File management
- **chroma_server** (port 6003) - Vector database
- **billing_server** (port 6004) - Billing logic
- **git_server** (port 6005) - Git versioning

## 🚀 Getting Started

### Prerequisites
- Docker and Docker Compose installed
- Node.js modules installed in `./frontend` (run `npm install`)
- Python requirements installed locally for IDE support (optional)

### Starting the Development Environment

From the project root:

```bash
docker compose -f docker-compose.dev.yml up --build
```

**First time?** Add `--build` to build all images:
```bash
docker compose -f docker-compose.dev.yml up --build
```

**Subsequently?** Just start:
```bash
docker compose -f docker-compose.dev.yml up
```

### Stopping Everything

```bash
docker compose -f docker-compose.dev.yml down
```

### View Logs

All services:
```bash
docker compose -f docker-compose.dev.yml logs -f
```

Specific service:
```bash
docker compose -f docker-compose.dev.yml logs -f backend
```

## 📊 Service Connectivity Map

```
Frontend (5173) 
    ↓
Backend (5000) ← Your API calls go here
    ↓
    ├→ Auth (6001)
    ├→ Filesystem (6002)
    ├→ Chroma (6003)
    ├→ Billing (6004)
    └→ Git (6005)
```

**Important**: Only the Frontend and Backend are exposed to the outside world. All microservices are internal and only accessible from the Backend.

## 🔄 Development Workflow

### Frontend Changes
1. Edit files in `./frontend/src/`
2. Vite detects changes and hot-reloads
3. Browser automatically updates (no manual refresh needed)

### Backend Changes
1. Edit files in `./backend/`
2. Flask detects changes and reloads
3. Test your changes via API calls

### Microservice Changes
1. Edit files in respective service directory
2. Container auto-restarts on file changes
3. Changes take effect immediately

## 📝 Environment Variables

Backend environment variables (set in docker-compose.dev.yml):
- `FLASK_ENV=development` - Enables debug mode and auto-reload
- `AUTH_SERVER_URL=http://auth:6001`
- `FILESYSTEM_SERVER_URL=http://filesystem:6002`
- `CHROMA_SERVER_URL=http://chroma:6003`
- `BILLING_SERVER_URL=http://billing:6004`
- `GIT_SERVER_URL=http://git:6005`

Frontend environment variables:
- `VITE_BACKEND_URL=http://localhost:5000/v1/api` - Backend API endpoint

## 🐛 Troubleshooting

### Port Already in Use
If port 5000, 5173, or others are already in use:
```bash
# Change port in docker-compose.dev.yml and remap:
ports:
  - "5000:5000"  # Change first 5000 to a different port
```

### Service Won't Start
Check logs:
```bash
docker compose -f docker-compose.dev.yml logs backend
```

### Clean Rebuild
Remove all containers and images:
```bash
docker compose -f docker-compose.dev.yml down --rmi all
docker compose -f docker-compose.dev.yml up --build
```

### Permission Issues (Linux/Mac)
If you get permission denied errors:
```bash
sudo docker compose -f docker-compose.dev.yml up --build
```

## 📁 Project Structure

```
.
├── docker-compose.dev.yml     # This compose file
├── .dockerignore                # Docker build ignore rules
├── frontend/                    # React + Vite
│   └── package.json
├── backend/
│   ├── Dockerfile.dev          # Backend Docker image
│   ├── app.py                  # Flask app
│   └── requirements.txt
├── auth_server/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── filesystem_server/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── chroma_server/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── billing_server/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
└── git_server/
    ├── Dockerfile
    ├── app.py
    └── requirements.txt
```

## 🔗 Testing the Setup

### Check Frontend
```bash
curl http://localhost:5173
```

### Check Backend
```bash
curl http://localhost:5000/openapi.json
```

### Check Backend Can Reach Microservices
The backend will fail to start if it can't reach the services. Watch the logs:
```bash
docker compose -f docker-compose.dev.yml logs backend
```

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Flask Development Guide](https://flask.palletsprojects.com/en/latest/development/)
- [Vite Guide](https://vitejs.dev/guide/)
