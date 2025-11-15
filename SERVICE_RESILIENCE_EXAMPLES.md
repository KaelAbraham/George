# Resilient Service Communication Examples

This file shows practical examples of using ResilientServiceClient in the backend.

## Quick Start: Chat Endpoint with Resilience

```python
# backend/app.py - Example integration

from service_utils import ResilientServiceClient, ServiceUnavailable

# Initialize clients at module level
chroma_client = ResilientServiceClient(
    os.getenv("CHROMA_SERVER_URL", "http://chroma:6003"),
    service_name="Chroma Server",
    max_retries=3,
    timeout=10
)

filesystem_client = ResilientServiceClient(
    os.getenv("FILESYSTEM_SERVER_URL", "http://filesystem:6002"),
    service_name="Filesystem Server"
)

@app.route('/v1/api/chat', methods=['POST'])
def chat_with_resilience():
    """Chat endpoint with resilient service communication."""
    try:
        user_id = get_user_id_from_request(request)
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        
        data = request.get_json()
        message = data.get('message')
        
        # Step 1: Get context from vector store (with fallback)
        context = get_context_resilient(message, user_id)
        
        # Step 2: Generate response from LLM
        response_text = llm_client.generate(message, context)
        
        # Step 3: Save to filesystem (best effort)
        save_to_filesystem_resilient(user_id, message, response_text)
        
        return jsonify({
            "response": response_text,
            "context_sources": len(context)
        }), 200
        
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        return jsonify({"error": "Chat service error"}), 500


def get_context_resilient(query: str, user_id: str) -> list:
    """
    Get context from vector store with automatic fallback.
    
    Flow:
    1. Try vector search in Chroma
    2. If Chroma down: use full-text search
    3. If both fail: use empty context (LLM will respond without context)
    """
    try:
        response = chroma_client.post(
            "/query",
            json={
                "collection_name": f"project_{user_id}",
                "query_texts": [query],
                "n_results": 5
            }
        )
        results = response.json()
        logger.info(f"✓ Vector search found {len(results.get('documents', []))} results")
        return results.get('documents', [])
        
    except ServiceUnavailable:
        logger.warning("Vector search unavailable (circuit open), trying full-text fallback")
        return full_text_search(query, user_id)
        
    except requests.RequestException as e:
        logger.warning(f"Vector search failed: {e}, trying full-text fallback")
        return full_text_search(query, user_id)


def full_text_search(query: str, user_id: str) -> list:
    """Fallback full-text search when vector store is down."""
    try:
        # Try to get documents from filesystem
        response = filesystem_client.get(
            f"/projects/{user_id}/search?q={query}",
            timeout=5
        )
        docs = response.json().get('results', [])
        logger.info(f"✓ Full-text search found {len(docs)} results")
        return docs
    except Exception as e:
        logger.warning(f"Full-text search also failed: {e}, proceeding without context")
        return []


def save_to_filesystem_resilient(user_id: str, query: str, response: str) -> bool:
    """
    Save message to filesystem (best effort, doesn't fail the chat).
    
    Returns:
        bool: True if saved, False otherwise
    """
    try:
        headers = {"X-User-ID": user_id}
        filesystem_client.post(
            "/save_file",
            json={
                "project_id": user_id,
                "file_path": "chat_history.md",
                "content": f"\n\n## User\n{query}\n\n## AI\n{response}"
            },
            headers=headers,
            timeout=10
        )
        logger.debug("✓ Saved to filesystem")
        return True
        
    except ServiceUnavailable:
        logger.warning("Filesystem service down (circuit open), chat saved in memory")
        return False
        
    except requests.RequestException as e:
        logger.warning(f"Failed to save to filesystem: {e}, continuing")
        return False
```

## Example 2: Async Job Processing with Resilience

```python
# backend/ingestion_worker.py - Resilient background jobs

class IngestionWorker:
    def __init__(self):
        self.filesystem_client = ResilientServiceClient(
            os.getenv("FILESYSTEM_SERVER_URL", "http://filesystem:6002"),
            service_name="Filesystem Server"
        )
        self.chroma_client = ResilientServiceClient(
            os.getenv("CHROMA_SERVER_URL", "http://chroma:6003"),
            service_name="Chroma Server"
        )
        self.git_client = ResilientServiceClient(
            os.getenv("GIT_SERVER_URL", "http://git:6005"),
            service_name="Git Server"
        )
    
    def ingest_documents(self, project_id: str, documents: list) -> dict:
        """
        Ingest documents with resilient service communication.
        
        Strategy:
        - Critical: Vector indexing (fail if Chroma is down)
        - Important: File saving (warn but continue)
        - Nice-to-have: Git snapshots (log warning, continue)
        """
        results = {
            "saved": 0,
            "indexed": 0,
            "git_failed": False
        }
        
        for doc in documents:
            # Step 1: Save to filesystem (best effort)
            try:
                self.filesystem_client.post(
                    "/save_file",
                    json={
                        "project_id": project_id,
                        "file_path": f"docs/{doc['filename']}",
                        "content": doc['content']
                    },
                    timeout=20
                )
                results["saved"] += 1
            except ServiceUnavailable:
                self.logger.warning(f"Filesystem down, skipping save for {doc['filename']}")
            except requests.RequestException as e:
                self.logger.warning(f"Failed to save {doc['filename']}: {e}")
            
            # Step 2: Index in vector store (critical)
            try:
                self.chroma_client.post(
                    "/add_chunks",
                    json={
                        "collection_name": f"project_{project_id}",
                        "chunks": [{
                            "text": doc['content'],
                            "id": doc['id'],
                            "metadata": {"filename": doc['filename']}
                        }]
                    },
                    timeout=15
                )
                results["indexed"] += 1
            except ServiceUnavailable:
                self.logger.error("Chroma service down - cannot index documents")
                # This is critical, we should fail the job
                raise Exception("Vector database unavailable")
            except requests.RequestException as e:
                self.logger.error(f"Failed to index {doc['filename']}: {e}")
                raise Exception(f"Indexing failed: {e}")
        
        # Step 3: Create git snapshot (nice-to-have)
        try:
            self.git_client.post(
                f"/snapshot/{project_id}",
                json={
                    "message": f"Ingested {results['indexed']} documents"
                },
                timeout=30
            )
        except ServiceUnavailable:
            self.logger.warning("Git service down, skipping snapshot")
            results["git_failed"] = True
        except requests.RequestException as e:
            self.logger.warning(f"Failed to create git snapshot: {e}")
            results["git_failed"] = True
        
        return results
```

## Example 3: Monitoring Endpoint

```python
# backend/app.py - Service health monitoring

@app.route('/v1/api/status/services', methods=['GET'])
@app.route('/admin/service-status', methods=['GET'])
def service_status():
    """
    Get status of all internal services for monitoring.
    
    Shows circuit breaker state, failure counts, and last state changes.
    Use this for health dashboards and alerting.
    """
    return jsonify({
        "services": {
            "chroma": chroma_client.get_status(),
            "filesystem": filesystem_client.get_status(),
            "billing": billing_client.get_status(),
            "git": git_client.get_status()
        },
        "timestamp": datetime.now().isoformat()
    }), 200


# Example response:
{
    "services": {
        "chroma": {
            "service": "Chroma Server",
            "state": "closed",
            "failure_count": 0,
            "last_failure": null,
            "last_state_change": "2025-11-15T10:30:45.123456"
        },
        "filesystem": {
            "service": "Filesystem Server",
            "state": "half_open",
            "failure_count": 1,
            "last_failure": "2025-11-15T10:32:12.456789",
            "last_state_change": "2025-11-15T10:32:00.000000"
        },
        "billing": {
            "service": "Billing Server",
            "state": "closed",
            "failure_count": 0,
            "last_failure": null,
            "last_state_change": "2025-11-15T09:15:20.000000"
        },
        "git": {
            "service": "Git Server",
            "state": "open",
            "failure_count": 0,
            "last_failure": "2025-11-15T10:20:30.987654",
            "last_state_change": "2025-11-15T10:20:30.987654"
        }
    },
    "timestamp": "2025-11-15T10:33:00.000000"
}
```

## Example 4: Error Handling Patterns

```python
# Pattern 1: Fail Open with Fallback (Non-critical)
@app.route('/v1/api/search', methods=['POST'])
def search():
    query = request.json.get('query')
    
    try:
        response = chroma_client.post("/query", json={"query_texts": [query]})
        return response.json(), 200
    except ServiceUnavailable:
        logger.info("Vector search unavailable, using cache")
        return cache.get_search_results(query, default=[]), 200


# Pattern 2: Fail Closed with Error (Critical)
@app.route('/v1/api/billing/deduct', methods=['POST'])
def deduct_cost():
    amount = request.json.get('amount')
    
    try:
        response = billing_client.post(
            "/deduct",
            json={"amount": amount},
            timeout=5
        )
        return response.json(), 200
    except ServiceUnavailable:
        logger.error("Billing service unavailable")
        return {"error": "Cannot process billing"}, 503
    except requests.RequestException as e:
        logger.error(f"Billing failed: {e}")
        return {"error": "Billing service error"}, 503


# Pattern 3: Best Effort, Log and Continue (Optional)
def save_metadata(data):
    """Save metadata - if it fails, the main operation continues."""
    try:
        filesystem_client.post(
            "/save_file",
            json=data,
            timeout=10
        )
        return True
    except ServiceUnavailable:
        logger.debug("Filesystem down, skipping metadata save")
        return False
    except requests.RequestException as e:
        logger.debug(f"Metadata save failed: {e}")
        return False
```

## Example 5: Testing with Mocks

```python
# tests/test_resilience.py

import pytest
from unittest.mock import patch, MagicMock
from backend.app import chat_with_resilience, get_context_resilient
from service_utils import ServiceUnavailable

def test_chat_with_chroma_down():
    """Test that chat still works when Chroma is down (uses fallback)."""
    with patch('backend.app.chroma_client') as mock_chroma:
        mock_chroma.post.side_effect = ServiceUnavailable("Chroma down")
        
        response = chat_with_resilience("hello", "user123")
        
        # Should still work, using fallback search
        assert response.status_code == 200


def test_chat_with_all_services_down():
    """Test graceful degradation when all services fail."""
    with patch('backend.app.chroma_client') as mock_chroma:
        with patch('backend.app.filesystem_client') as mock_fs:
            mock_chroma.post.side_effect = ServiceUnavailable("Chroma down")
            mock_fs.get.side_effect = ServiceUnavailable("Filesystem down")
            
            response = chat_with_resilience("hello", "user123")
            
            # Chat should still return something (LLM response without context)
            assert response.status_code == 200


def test_circuit_breaker_prevents_hammering():
    """Test that circuit breaker stops hammering failing service."""
    client = ResilientServiceClient(
        "http://failing:9999",
        failure_threshold=2,
        max_retries=1
    )
    
    with patch('requests.request') as mock_request:
        mock_request.side_effect = ConnectionError()
        
        # Make requests until circuit opens
        for i in range(2):
            with pytest.raises(ConnectionError):
                client.post("/test")
        
        # Next request should fail immediately without attempting
        with pytest.raises(ServiceUnavailable):
            client.post("/test")
        
        # Verify only 2 requests were made (not 3+)
        assert mock_request.call_count == 2
```

## Implementation Checklist

- [ ] Add `ResilientServiceClient` to `backend/service_utils.py` ✓
- [ ] Initialize clients for all services in `backend/app.py`
- [ ] Replace direct `requests.post()` calls with client methods
- [ ] Add error handling for `ServiceUnavailable` exceptions
- [ ] Implement fallback strategies for non-critical operations
- [ ] Add monitoring endpoint (`/v1/api/status/services`)
- [ ] Test circuit breaker behavior
- [ ] Update deployment documentation
- [ ] Monitor circuit breaker states in production
- [ ] Set up alerting for circuit breaker opens

## See Also

- `SERVICE_RESILIENCE_GUIDE.md` - Detailed guide
- `backend/service_utils.py` - Implementation
- `backend/app.py` - Integration examples
