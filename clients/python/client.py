"""
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
