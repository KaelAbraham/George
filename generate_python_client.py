"""
Manual OpenAPI Python Client Generator
Generates a type-safe Python client from the OpenAPI spec
"""
import json
from pathlib import Path
from datetime import datetime

# Read the OpenAPI spec
spec_path = Path(__file__).parent / "api_spec.json"
with open(spec_path) as f:
    spec = json.load(f)

# Create clients directory
clients_dir = Path(__file__).parent / "clients" / "python"
clients_dir.mkdir(parents=True, exist_ok=True)

# Generate models.py
models_py = '''"""
Auto-generated data models from OpenAPI spec
"""
from typing import Optional, Any, Dict, List
from dataclasses import dataclass, asdict
import json
from datetime import datetime

@dataclass
class ChatRequest:
    """Request model for POST /chat"""
    query: str
    project_id: str

@dataclass
class ChatResponse:
    """Response model for POST /chat"""
    response: str
    intent: str
    cost: float
    downgraded: bool
    balance: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values"""
        return {k: v for k, v in asdict(self).items() if v is not None}

@dataclass
class JobStatus:
    """Job status information"""
    job_id: str
    project_id: str
    user_id: str
    status: str  # pending, running, completed, failed
    job_type: str
    created_at: str
    result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values"""
        return {k: v for k, v in asdict(self).items() if v is not None}

@dataclass
class JobsList:
    """List of jobs for a project"""
    project_id: str
    jobs: List[JobStatus]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "project_id": self.project_id,
            "jobs": [job.to_dict() for job in self.jobs]
        }

@dataclass
class WikiGenerationResponse:
    """Response for wiki generation request"""
    message: str
    job_id: str
    status_url: str

@dataclass
class CostSummary:
    """Cost summary for all LLM clients"""
    total_tokens: int
    total_cost: float
    clients: Dict[str, Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "clients": self.clients
        }
'''

(clients_dir / "models.py").write_text(models_py)
print(f"✓ Created {clients_dir / 'models.py'}")

# Generate client.py
client_py = '''"""
Auto-generated API Client for Caudex Pro AI Router
Provides type-safe HTTP client for all endpoints
"""
import requests
import json
from typing import Optional, Dict, Any
from .models import (
    ChatRequest, ChatResponse,
    JobStatus, JobsList,
    WikiGenerationResponse,
    CostSummary
)

class CaudexAPIClient:
    """Type-safe API client for Caudex Pro AI Router"""
    
    def __init__(self, base_url: str = "http://localhost:5001", timeout: int = 30):
        """
        Initialize the API client.
        
        Args:
            base_url: Base URL of the API server
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
    
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make an HTTP request to the API"""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    
    # Chat Endpoints
    
    def post_chat(self, query: str, project_id: str) -> ChatResponse:
        """
        Post a chat query to the AI router.
        
        Args:
            query: The user's query
            project_id: Project ID
            
        Returns:
            ChatResponse with AI response and metadata
        """
        payload = ChatRequest(query=query, project_id=project_id)
        response = self._request(
            "POST",
            "/chat",
            json={"query": payload.query, "project_id": payload.project_id},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        return ChatResponse(
            response=data["response"],
            intent=data["intent"],
            cost=data["cost"],
            downgraded=data["downgraded"],
            balance=data.get("balance")
        )
    
    # Job Endpoints
    
    def get_job_status(self, job_id: str) -> JobStatus:
        """
        Get the status of a specific job.
        
        Args:
            job_id: The job ID
            
        Returns:
            JobStatus with job information
        """
        response = self._request("GET", f"/jobs/{job_id}")
        data = response.json()
        return JobStatus(
            job_id=data["job_id"],
            project_id=data["project_id"],
            user_id=data["user_id"],
            status=data["status"],
            job_type=data["job_type"],
            created_at=data["created_at"],
            result=data.get("result")
        )
    
    def get_project_jobs(self, project_id: str) -> JobsList:
        """
        Get all jobs for a specific project.
        
        Args:
            project_id: The project ID
            
        Returns:
            JobsList containing all jobs for the project
        """
        response = self._request("GET", f"/project/{project_id}/jobs")
        data = response.json()
        jobs = [
            JobStatus(
                job_id=j["job_id"],
                project_id=j["project_id"],
                user_id=j["user_id"],
                status=j["status"],
                job_type=j["job_type"],
                created_at=j["created_at"],
                result=j.get("result")
            )
            for j in data["jobs"]
        ]
        return JobsList(project_id=data["project_id"], jobs=jobs)
    
    def generate_wiki(self, project_id: str) -> WikiGenerationResponse:
        """
        Generate wiki documentation for a project.
        
        Args:
            project_id: The project ID
            
        Returns:
            WikiGenerationResponse with job info
        """
        response = self._request("POST", f"/project/{project_id}/generate_wiki")
        data = response.json()
        return WikiGenerationResponse(
            message=data["message"],
            job_id=data["job_id"],
            status_url=data["status_url"]
        )
    
    # Admin Endpoints
    
    def get_admin_costs(self) -> CostSummary:
        """
        Get cost summary for all LLM clients.
        Requires admin access.
        
        Returns:
            CostSummary with aggregate cost information
        """
        response = self._request("GET", "/admin/costs")
        data = response.json()
        return CostSummary(
            total_tokens=data["total_tokens"],
            total_cost=data["total_cost"],
            clients=data["clients"]
        )
    
    def close(self):
        """Close the HTTP session"""
        self.session.close()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

__all__ = ["CaudexAPIClient"]
'''

(clients_dir / "client.py").write_text(client_py)
print(f"✓ Created {clients_dir / 'client.py'}")

# Generate __init__.py
init_py = '''"""
Caudex Pro AI Router Python Client
Auto-generated from OpenAPI specification
"""
from .client import CaudexAPIClient
from .models import (
    ChatRequest, ChatResponse,
    JobStatus, JobsList,
    WikiGenerationResponse,
    CostSummary
)

__version__ = "1.0.0"
__all__ = [
    "CaudexAPIClient",
    "ChatRequest", "ChatResponse",
    "JobStatus", "JobsList",
    "WikiGenerationResponse",
    "CostSummary"
]
'''

(clients_dir / "__init__.py").write_text(init_py)
print(f"✓ Created {clients_dir / '__init__.py'}")

# Generate requirements.txt for the client
requirements_txt = '''requests>=2.28.0
'''

(clients_dir / "requirements.txt").write_text(requirements_txt)
print(f"✓ Created {clients_dir / 'requirements.txt'}")

# Generate example usage
example_py = '''"""
Example usage of the Caudex Pro AI Router Python client
"""
from caudex_client import CaudexAPIClient

def main():
    # Initialize the client
    with CaudexAPIClient() as client:
        try:
            # Example 1: Chat query
            print("\\n=== Chat Query ===")
            response = client.post_chat(
                query="What is the purpose of this project?",
                project_id="project-123"
            )
            print(f"Response: {response.response}")
            print(f"Intent: {response.intent}")
            print(f"Cost: {response.cost}")
            print(f"Downgraded: {response.downgraded}")
            
            # Example 2: Get job status
            print("\\n=== Get Job Status ===")
            job_status = client.get_job_status("job-123")
            print(f"Job ID: {job_status.job_id}")
            print(f"Status: {job_status.status}")
            print(f"Type: {job_status.job_type}")
            
            # Example 3: Get project jobs
            print("\\n=== Get Project Jobs ===")
            jobs_list = client.get_project_jobs("project-123")
            print(f"Project: {jobs_list.project_id}")
            print(f"Number of jobs: {len(jobs_list.jobs)}")
            for job in jobs_list.jobs:
                print(f"  - {job.job_id}: {job.status}")
            
            # Example 4: Admin costs
            print("\\n=== Admin Costs ===")
            costs = client.get_admin_costs()
            print(f"Total tokens: {costs.total_tokens}")
            print(f"Total cost: ${costs.total_cost}")
            for client_name, metrics in costs.clients.items():
                print(f"  {client_name}: {metrics}")
        
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
'''

(clients_dir / "example.py").write_text(example_py)
print(f"✓ Created {clients_dir / 'example.py'}")

# Generate README
readme_md = '''# Caudex Pro AI Router Python Client

Auto-generated type-safe Python client for the Caudex Pro AI Router API.

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from caudex_client import CaudexAPIClient

# Initialize client
client = CaudexAPIClient(base_url="http://localhost:5001")

# Post a chat query
response = client.post_chat(
    query="What is the project structure?",
    project_id="my-project"
)
print(response.response)

# Get job status
job_status = client.get_job_status("job-id")
print(f"Status: {job_status.status}")

# Use as context manager for automatic cleanup
with CaudexAPIClient() as client:
    costs = client.get_admin_costs()
    print(f"Total API cost: ${costs.total_cost}")
```

## API Reference

### ChatRequest / ChatResponse

```python
response = client.post_chat(
    query: str,           # User query
    project_id: str       # Project ID
) -> ChatResponse
```

### Job Management

```python
# Get single job status
status = client.get_job_status(job_id: str) -> JobStatus

# Get all project jobs
jobs = client.get_project_jobs(project_id: str) -> JobsList

# Generate wiki (async, returns 202)
result = client.generate_wiki(project_id: str) -> WikiGenerationResponse
```

### Admin Endpoints

```python
# Get cost summary (requires admin access)
costs = client.get_admin_costs() -> CostSummary
```

## Model Classes

- `ChatRequest`: Request payload for chat endpoint
- `ChatResponse`: Response from chat endpoint
- `JobStatus`: Individual job information
- `JobsList`: Collection of jobs for a project
- `WikiGenerationResponse`: Async wiki generation response
- `CostSummary`: Cost aggregation across LLM clients

All model classes include:
- Type hints for all fields
- Optional fields with `Optional[T]` type hints
- `to_dict()` methods for serialization

## Error Handling

```python
from requests.exceptions import RequestException, HTTPError

try:
    response = client.post_chat(query="...", project_id="...")
except HTTPError as e:
    print(f"HTTP error: {e.response.status_code}")
except RequestException as e:
    print(f"Request error: {e}")
```

## Generated

- **Date**: ''' + datetime.now().isoformat() + '''
- **From**: api_spec.json (OpenAPI 3.0.2)
- **Generator**: Python auto-generator script
'''

(clients_dir / "README.md").write_text(readme_md)
print(f"✓ Created {clients_dir / 'README.md'}")

print(f"\\n✅ Python API client generated successfully!")
print(f"   Location: {clients_dir}")
print(f"   Files:")
print(f"     - models.py (data classes)")
print(f"     - client.py (API client)")
print(f"     - __init__.py (package)")
print(f"     - example.py (usage example)")
print(f"     - requirements.txt")
print(f"     - README.md")
