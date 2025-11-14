# Save as Note Feature - Implementation Complete

## Overview

The "Save as Note" feature is a power-user capability that allows users to directly ingest a chat response into their project's knowledge base by marking it as a saved note. This creates a "retention-first" workflow where valuable AI insights become permanent project documentation.

## Architecture

This feature follows the **Contract-Driven Development** (Workflow A) model:

```
User clicks "Save" → Backend validates & saves → Knowledge Base updated → Frontend auto-updated
```

### Step 1: Backend Implementation ✅

#### New Database Method: `SessionManager.get_turn_by_id()`

**File:** `backend/session_manager.py`

```python
def get_turn_by_id(self, message_id: str, user_id: str) -> Optional[Dict]:
    """
    Retrieves a single chat turn (query, response, project_id) by its unique message_id,
    ensuring the user has permission to access it.
    """
```

**Features:**
- Secure retrieval with user_id verification (prevents cross-user access)
- Returns: `{project_id, user_query, ai_response}`
- Returns `None` if message not found or user lacks permission

#### New API Schema: `SaveNoteResponseSchema`

**File:** `backend/app.py`

```python
class SaveNoteResponseSchema(ma.Schema):
    """Response schema for successful note saving."""
    status = ma.fields.Str()
    note_path = ma.fields.Str()
    ingest_status = ma.fields.Str()
```

#### New API Endpoint: `POST /chat/<message_id>/save_as_note`

**File:** `backend/app.py` - Class `SaveChatNote(MethodView)`

**Route:** `POST /chat/<string:message_id>/save_as_note`

**Request:**
- **Authentication:** Bearer token required (Authorization header)
- **Path Parameter:** `message_id` (unique ID from chat response)
- **Body:** None (data comes from message_id lookup)

**Response (201 Created):**
```json
{
  "status": "success",
  "note_path": "notes/note_msg_abc123def456.md",
  "ingest_status": "success"
}
```

**Logic Flow:**
1. Authenticate user from request token
2. Retrieve chat turn data securely via `get_turn_by_id(message_id, user_id)`
3. Format content as Markdown:
   ```markdown
   # Saved Chat Note (2025-11-13 14:30)
   
   This note was saved directly from a chat session.
   
   ## User Prompt
   [User's original query]
   
   ## George's Response
   [AI response text]
   ```
4. Save file to filesystem via `filesystem_server` microservice
5. Ingest note into Chroma knowledge base collection for the project
6. Return status and file path

**Error Handling:**
- 401: Invalid or missing token
- 404: Chat message not found or user lacks permission
- 500: Microservice failure (filesystem or Chroma)
- 503: Knowledge base temporarily unavailable

### Step 2: API Client Regeneration ✅

Since Java compatibility issues prevented using `openapi-generator-cli`, the frontend API client was manually updated to reflect the new backend contract.

#### Updated Models: `frontend/src/api-client/models.ts`

```typescript
export interface ChatResponse {
  messageId: string;              // NEW: Unique message ID
  response: string;
  intent: string;
  cost: number;
  downgraded: boolean;
  balance?: number | null;
}

export interface FeedbackRequest {
  message_id: string;
  rating: number;
  category?: string | null;
  comment?: string | null;
}

export interface FeedbackResponse {
  status: string;
  feedback_id: string;
}

export interface SaveNoteResponse {
  status: string;
  note_path: string;
  ingest_status: string;
}
```

#### New Client Methods: `frontend/src/api-client/client.ts`

```typescript
async postFeedback(feedback: FeedbackRequest): Promise<FeedbackResponse>
async saveMessageAsNote(messageId: string): Promise<SaveNoteResponse>
```

#### New API Functions: `frontend/src/api-client/api.ts`

```typescript
export async function postFeedback(feedback: FeedbackRequest): Promise<FeedbackResponse>
export async function saveMessageAsNote(messageId: string): Promise<SaveNoteResponse>
```

### Step 3: Frontend Integration ✅

#### Example Component: `ChatBubbleWithSaveNote.tsx`

**Location:** `frontend/src/ChatBubbleWithSaveNote.tsx`

**Features:**
- Displays chat bubble with message content
- Three action buttons:
  1. 👍 - Mark as helpful (feedback)
  2. 👎 - Mark as not helpful (feedback)
  3. 🔖 - **Save as Note** (NEW)
- Status indicators showing success/error messages
- Loading state management during API calls

**Usage:**
```tsx
import ChatBubble from './ChatBubbleWithSaveNote';

<ChatBubble 
  message={chatResponse}
  onNoteSaved={(notePath) => console.log(`Saved to ${notePath}`)}
  onFeedbackSubmitted={(feedbackId) => console.log(`Feedback ${feedbackId}`)}
/>
```

**Event Handlers:**
```typescript
handleSaveAsNote = async (messageId: string) => {
  try {
    const response = await saveMessageAsNote(messageId);
    console.log("Note saved!", response.data);
    // Show success toast
  } catch (error) {
    console.error("Failed to save note", error);
    // Show error toast
  }
};
```

## Data Flow

### Full Request/Response Cycle

```
1. USER ACTION
   └─ Clicks 🔖 button on chat bubble
      └─ Has access to message.messageId

2. FRONTEND
   └─ Calls saveMessageAsNote(messageId)
      └─ Makes POST /chat/{messageId}/save_as_note

3. BACKEND AUTHORIZATION
   └─ Verifies Authorization header
      └─ Extracts user_id from token

4. BACKEND RETRIEVAL
   └─ Calls session_manager.get_turn_by_id(messageId, user_id)
      └─ Confirms user owns this message
      └─ Returns {project_id, user_query, ai_response}

5. BACKEND ORCHESTRATION
   ├─ Formats Markdown note
   ├─ Calls filesystem_server to save file
   │  └─ POST /save_file with note content
   ├─ Calls chroma_server to ingest
   │  └─ POST /add with document for indexing
   └─ Logs success

6. FRONTEND RESPONSE
   └─ Receives {status, note_path, ingest_status}
      └─ Shows "Note saved!" indicator
      └─ Updates UI state
```

## Database Schema

### Session History (Existing with new field)

**Table:** `chat_history`

```sql
CREATE TABLE chat_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT,                    -- NEW: Unique ID for AI responses
  project_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,                 -- 'user' or 'model'
  content TEXT NOT NULL,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_message_id ON chat_history (message_id);
```

### Knowledge Base (Existing)

**Service:** Chroma (Vector DB)

**Collection:** `project_{project_id}`

**New Document Metadata:**
```json
{
  "source_file": "notes/note_msg_abc123.md",
  "type": "saved_note",
  "created_at": "2025-11-13T14:30:00Z"
}
```

## Security Considerations

✅ **User Isolation:**
- `get_turn_by_id()` verifies both `message_id` AND `user_id`
- Cannot access another user's messages
- 404 response (indistinguishable from missing message)

✅ **Authentication:**
- Bearer token required for endpoint
- User ID extracted from token claims
- 401 if token invalid/missing

✅ **Data Integrity:**
- Message ID is immutable (UUID format)
- Note saved to user's project directory only
- Chroma collection scoped to project

✅ **Microservice Resilience:**
- Filesystem save failure doesn't block response
- Chroma ingest logged but continues
- 500 error only if critical failure
- Graceful degradation with warnings

## File Locations

After saving a note:

```
project/
├── notes/
│   ├── note_msg_abc123def456.md       ← Saved here
│   ├── note_msg_xyz789uvw123.md
│   └── ...
├── documents/
├── characters/
└── ...
```

## Testing

### Backend Test (cURL)

```bash
# Get a valid message_id from a chat response
curl -X POST http://localhost:5000/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Test query", "project_id": "proj_123"}'

# Response includes messageId
# {
#   "messageId": "msg_12345678-1234-1234-1234-123456789abc",
#   "response": "...",
#   ...
# }

# Save the response as a note
curl -X POST "http://localhost:5000/chat/msg_12345678-1234-1234-1234-123456789abc/save_as_note" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Response
# {
#   "status": "success",
#   "note_path": "notes/note_msg_12345678-1234-1234-1234-123456789abc.md",
#   "ingest_status": "success"
# }
```

### Frontend Test (TypeScript)

```typescript
import { saveMessageAsNote } from './api-client';

const response = await saveMessageAsNote('msg_12345678-1234-1234-1234-123456789abc');
console.log(response);
// {
//   status: 'success',
//   note_path: 'notes/note_msg_12345678-1234-1234-1234-123456789abc.md',
//   ingest_status: 'success'
// }
```

## Usage Examples

### Basic Integration

```tsx
import { saveMessageAsNote } from './api-client';

const handleSaveNote = async (messageId: string) => {
  try {
    const result = await saveMessageAsNote(messageId);
    toast.success(`Note saved to ${result.note_path}`);
  } catch (error) {
    toast.error('Failed to save note');
  }
};
```

### With Feedback

```tsx
import { postFeedback, saveMessageAsNote } from './api-client';

const handleAction = async (messageId: string, action: 'helpful' | 'save') => {
  if (action === 'helpful') {
    await postFeedback({
      message_id: messageId,
      rating: 1,
      category: 'accurate'
    });
  } else if (action === 'save') {
    await saveMessageAsNote(messageId);
  }
};
```

### Advanced: Batch Operations

```typescript
async function saveAllHelpfulResponses(messages: ChatResponse[]) {
  const results = await Promise.allSettled(
    messages
      .filter(m => m.wasMarkedHelpful)
      .map(m => saveMessageAsNote(m.messageId))
  );
  
  const saved = results.filter(r => r.status === 'fulfilled').length;
  console.log(`Saved ${saved} notes to knowledge base`);
}
```

## Workflow Benefits

### For Users
- ✅ Easy knowledge curation - just click 🔖
- ✅ Automatic knowledge base updates
- ✅ Full message history retained
- ✅ Notes become searchable via Chroma

### For Product
- ✅ Power-user retention feature
- ✅ Increases engagement with knowledge base
- ✅ Creates feedback loop: chat → learning → better responses
- ✅ Better personalization data

### For Engineering
- ✅ Contract-driven: Backend changes → Frontend auto-updates
- ✅ Microservice orchestration pattern
- ✅ Clean separation of concerns
- ✅ Extensible (can add more post-chat actions)

## Future Enhancements

1. **Batch Save:** Save multiple responses at once
2. **Custom Tags:** Allow users to tag notes before saving
3. **Scheduled Export:** Regular exports to note file
4. **Note Editing:** Allow editing saved notes before ingestion
5. **Analytics:** Track which responses are most frequently saved
6. **Templates:** Pre-formatted note templates based on message type

## Files Changed

```
backend/
├── session_manager.py           (+53 lines) - get_turn_by_id() method
└── app.py                       (+107 lines) - SaveNoteResponseSchema & SaveChatNote endpoint

frontend/
├── src/api-client/
│   ├── models.ts               (+28 lines) - New models: FeedbackRequest, SaveNoteResponse
│   ├── client.ts               (+41 lines) - postFeedback(), saveMessageAsNote() methods
│   └── api.ts                  (+23 lines) - New high-level API functions
└── src/ChatBubbleWithSaveNote.tsx (NEW)   - Example component

Total: ~252 lines of new/modified code
```

## Status

✅ **Backend:** Fully implemented and tested
✅ **Frontend Client:** Updated with new methods and models
✅ **Example Component:** Created and documented
✅ **Git Commit:** Changes pushed to repository

🚀 **Ready for Frontend Development:** Product and design teams can now integrate the 🔖 button into chat bubbles!
