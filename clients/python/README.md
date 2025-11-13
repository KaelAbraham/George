# Caudex Pro AI Router Python Client

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

- **Generated**: November 13, 2025
- **From**: api_spec.json (OpenAPI 3.0.2)
- **Generator**: Python client generator script
