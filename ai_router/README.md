# AI-Router Service

The central orchestration service for George. This service is the only thing the front-end will ever talk to. It does NOT touch files or databases directly; it only orchestrates the "Hands" (Phase 1 services) to get its job done.

## Architecture

The AI-Router implements a stateless chat loop:

1. **Receive Message**: Gets user's query and project ID
2. **Analyze Intent**: Uses Gemini Flash Lite to determine intent (Fact-Checking, Craft, or Support)
3. **Query KBs**: Makes HTTP call to chroma-core/mcp-server to get relevant context chunks
4. **Assemble "Georgeified" Prompt**: Wraps context in the "constitution" to enforce core philosophy
5. **Get Answer**: Uses Gemini Flash Lite to generate response with the safe, "Georgeified" prompt
6. **Return Response**: Sends the pure, stateless answer back to the user

## Services Orchestrated

- **filesystem-server** (port 5001): File operations
- **chroma-core/mcp-server** (port 5002): Vector database queries
- **git-server** (port 5003): Version control operations

## Environment Variables

- `FILESYSTEM_SERVER_URL`: Default `http://localhost:5001`
- `CHROMA_SERVER_URL`: Default `http://localhost:5002`
- `GIT_SERVER_URL`: Default `http://localhost:5003`
- `GEMINI_API_KEY`: Required for LLM operations

## Installation

```bash
pip install -r requirements.txt
```

## Running

```bash
python app.py
```

The service will start on `http://0.0.0.0:5000`

## API Endpoints

### POST /chat

Main chat endpoint implementing the stateless chat loop.

**Request:**
```json
{
  "message": "What color are Edie's eyes?",
  "project_id": "my_project_123"
}
```

**Response:**
```json
{
  "response": "Edie has brown eyes.",
  "intent": "Fact-Checking",
  "context_used": true,
  "context_chunks_count": 3,
  "model": "gemini-flash-lite",
  "success": true
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "llm_available": true,
  "services": {
    "filesystem_server": "http://localhost:5001",
    "chroma_server": "http://localhost:5002",
    "git_server": "http://localhost:5003"
  }
}
```

## Georgeification Layer

The service enforces George's core philosophy through the "Georgeification" layer:

- **Never writes, rewrites, or suggests specific language** for the user's manuscript
- Provides **analysis, feedback, and guidance only**
- Follows the **George Operational Protocol** from `src/george/prompts/george_operational_protocol.txt`

This constitution is automatically loaded and applied to every query, ensuring consistency across all interactions.
