"""
Backend HTTP Client for UI Server

This module provides HTTP client wrappers for communicating with the backend services.
All backend operations (AI, knowledge extraction, project management) are accessed via HTTP.

Backend Services:
- Backend API: http://localhost:5001/api/
- ChromaDB Server: http://localhost:5002/
- Filesystem Server: http://localhost:5003/
"""

import requests
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# Backend service URLs
BACKEND_API_URL = "http://localhost:5001"
BACKEND_API_ENDPOINT = f"{BACKEND_API_URL}/api"


class BackendClient:
    """HTTP client for communicating with the backend services."""
    
    def __init__(self, base_url: str = BACKEND_API_ENDPOINT, timeout: int = 30):
        """
        Initialize the backend client.
        
        Args:
            base_url: Base URL for backend API (default: http://localhost:5001/api)
            timeout: Request timeout in seconds (default: 30)
        """
        self.base_url = base_url
        self.timeout = timeout
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        files: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the backend.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Form data to send
            json_data: JSON data to send
            params: Query parameters
            files: Files to upload
            headers: Custom headers
            
        Returns:
            Response JSON as dictionary
        """
        url = urljoin(self.base_url, endpoint)
        
        try:
            response = requests.request(
                method=method,
                url=url,
                data=data,
                json=json_data,
                params=params,
                files=files,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Backend connection error: {e}")
            return {"success": False, "error": f"Backend service unavailable: {e}"}
        except requests.exceptions.Timeout as e:
            logger.error(f"Backend request timeout: {e}")
            return {"success": False, "error": f"Backend request timed out: {e}"}
        except requests.exceptions.HTTPError as e:
            logger.error(f"Backend HTTP error: {e}")
            try:
                return response.json()
            except:
                return {"success": False, "error": f"Backend error: {e}"}
        except Exception as e:
            logger.error(f"Unexpected error during backend request: {e}")
            return {"success": False, "error": f"Unexpected error: {e}"}
    
    # --- Chat & Query Operations ---
    
    def query_knowledge_base(
        self,
        project_id: str,
        question: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Query the knowledge base using the backend AI router.
        
        Args:
            project_id: Project ID
            question: User's question
            user_id: User ID from Firebase
            
        Returns:
            Response with answer, sources, and metadata
        """
        return self._make_request(
            "POST",
            f"/projects/{project_id}/query",
            json_data={"question": question},
            headers={"Authorization": f"Bearer {user_id}"}
        )
    
    def upload_manuscript(
        self,
        project_id: str,
        file_path: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Upload a manuscript file to the backend.
        
        Args:
            project_id: Project ID
            file_path: Path to the manuscript file
            user_id: User ID from Firebase
            
        Returns:
            Response with upload status and file info
        """
        with open(file_path, 'rb') as f:
            files = {'file': f}
            return self._make_request(
                "POST",
                f"/projects/{project_id}/upload",
                files=files,
                headers={"Authorization": f"Bearer {user_id}"}
            )
    
    def generate_knowledge_base(
        self,
        project_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Trigger knowledge base generation for a project.
        
        Args:
            project_id: Project ID
            user_id: User ID from Firebase
            
        Returns:
            Response with generation status
        """
        return self._make_request(
            "POST",
            f"/projects/{project_id}/process",
            headers={"Authorization": f"Bearer {user_id}"}
        )
    
    # --- Project Operations ---
    
    def create_project(
        self,
        project_name: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Create a new project via the backend.
        
        Args:
            project_name: Name of the project
            user_id: User ID from Firebase
            
        Returns:
            Response with project info
        """
        return self._make_request(
            "POST",
            "/projects/create",
            json_data={"name": project_name},
            headers={"Authorization": f"Bearer {user_id}"}
        )
    
    def list_projects(self, user_id: str) -> Dict[str, Any]:
        """
        Get list of projects for a user.
        
        Args:
            user_id: User ID from Firebase
            
        Returns:
            Response with project list
        """
        return self._make_request(
            "GET",
            "/projects/list",
            headers={"Authorization": f"Bearer {user_id}"}
        )
    
    def get_project(self, project_id: str, user_id: str) -> Dict[str, Any]:
        """
        Get details of a specific project.
        
        Args:
            project_id: Project ID
            user_id: User ID from Firebase
            
        Returns:
            Response with project details
        """
        return self._make_request(
            "GET",
            f"/projects/{project_id}",
            headers={"Authorization": f"Bearer {user_id}"}
        )
    
    # --- Status & Health Checks ---
    
    def check_health(self) -> Dict[str, Any]:
        """
        Check if the backend is running and responsive.
        
        Returns:
            Response with backend status
        """
        return self._make_request("GET", "/status")
    
    def get_entities(self, project_id: str, user_id: str) -> Dict[str, Any]:
        """
        Get extracted entities for a project.
        
        Args:
            project_id: Project ID
            user_id: User ID from Firebase
            
        Returns:
            Response with entity list
        """
        return self._make_request(
            "GET",
            f"/projects/{project_id}/entities",
            headers={"Authorization": f"Bearer {user_id}"}
        )
    
    def get_status(self, project_id: str, user_id: str) -> Dict[str, Any]:
        """
        Get processing status for a project.
        
        Args:
            project_id: Project ID
            user_id: User ID from Firebase
            
        Returns:
            Response with processing status
        """
        return self._make_request(
            "GET",
            f"/projects/{project_id}/status",
            headers={"Authorization": f"Bearer {user_id}"}
        )


# Create a default client instance
backend_client = BackendClient()
