"""
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
