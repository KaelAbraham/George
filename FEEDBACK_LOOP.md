# Beta Tester Feedback Loop System

## Overview

Your application now has a complete feedback loop system for Beta testers. Every chat message gets a unique ID, and users can submit feedback on any message. This creates a tight feedback loop with your testers—your most valuable asset.

## Architecture

### Step 1: Message Tracking
Every response from `/chat` now includes a `message_id`:

```json
{
  "message_id": "msg_abc123-def456",
  "response": "Here's my answer...",
  "intent": "app_support",
  "cost": 0.005,
  "downgraded": false,
  "balance": 24.995
}
```

The message ID uniquely identifies that specific AI response and is stored in the database for future reference.

### Step 2: Feedback Submission
Beta testers can submit feedback using the new `/feedback` endpoint:

```bash
POST /feedback
Content-Type: application/json
Authorization: Bearer <token>

{
  "message_id": "msg_abc123-def456",
  "rating": 1,
  "category": "hallucination",
  "comment": "The AI incorrectly referenced a scene that doesn't exist in the manuscript."
}
```

**Request Schema:**
- `message_id` (required): The ID from the chat response
- `rating` (required): Integer value (e.g., 1 for good, -1 for bad, 0 for neutral)
- `category` (optional): Tag for categorizing feedback (e.g., "hallucination", "bad_tone", "off-topic", "other")
- `comment` (optional): Free-text feedback from the user

**Response (201 Created):**
```json
{
  "status": "success",
  "feedback_id": "fbk_xyz789-uvw012"
}
```

## Database Schema

### chat_history Table (Updated)
```
id              INTEGER PRIMARY KEY
message_id      TEXT (unique identifier for AI responses)
project_id      TEXT
user_id         TEXT
role            TEXT ("user" or "model")
content         TEXT (the message content)
timestamp       DATETIME
```

### feedback Table (New)
```
feedback_id     TEXT PRIMARY KEY
message_id      TEXT (foreign key to chat_history)
user_id         TEXT
rating          INTEGER
category        TEXT
comment         TEXT
timestamp       DATETIME
```

## Implemented Features

✅ **Message Tracking**
- Every chat response gets a unique `message_id`
- Message IDs are returned in the API response
- Messages are stored with their IDs in the database

✅ **Feedback Collection**
- New `/feedback` endpoint (POST) to accept feedback
- Authentication required (same as /chat)
- Feedback stored in dedicated `data/feedback.db`
- Feedback includes rating, category, and comments

✅ **API Documentation**
- Full Swagger UI documentation at `http://localhost:5000/api/docs`
- Both `/chat` and `/feedback` endpoints fully documented

✅ **FeedbackManager**
- Dedicated `FeedbackManager` class for all feedback operations
- Methods for saving, retrieving, and analyzing feedback
- Support for feedback summaries and analytics

## API Endpoints

### Chat Endpoint (Updated)
```
POST /chat
Response now includes: message_id
```

### New Feedback Endpoint
```
POST /feedback
Authentication: Required (Bearer token)
Body: FeedbackRequestSchema
Response: 201 Created with FeedbackResponseSchema
```

## Usage Flow for Beta Testers

1. **Tester sends a query:**
   ```
   POST /chat
   { "query": "How do I resolve the character conflict?", "project_id": "p-123" }
   ```

2. **Backend responds with message_id:**
   ```json
   {
     "message_id": "msg_550e8400-e29b-41d4-a716-446655440000",
     "response": "Here's my suggestion...",
     ...
   }
   ```

3. **Tester can provide feedback:**
   ```
   POST /feedback
   {
     "message_id": "msg_550e8400-e29b-41d4-a716-446655440000",
     "rating": 1,
     "category": "good_insight",
     "comment": "This really helped me think about the scene differently."
   }
   ```

4. **Feedback is stored and can be analyzed:**
   - View all feedback for a message
   - View all feedback from a specific user
   - Get feedback summary statistics

## Code Changes

### Files Modified
- `backend/session_manager.py` - Updated `add_turn()` to generate and return `message_id`
- `backend/app.py` - Updated `ChatResponseSchema`, added new `/feedback` endpoint, captured `message_id`

### Files Created
- `backend/feedback_manager.py` - Dedicated feedback management system
- `data/feedback.db` - Feedback database (auto-created on first run)

## Example Usage

### Step 1: Get an API token
```bash
curl -X POST http://localhost:5005/verify_token \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Step 2: Send a query
```bash
curl -X POST http://localhost:5000/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Help with my story", "project_id": "p-123"}'
```

Response:
```json
{
  "message_id": "msg_abc123",
  "response": "Here's how I can help...",
  "intent": "app_support",
  "cost": 0.005,
  "downgraded": false,
  "balance": 24.995
}
```

### Step 3: Submit feedback
```bash
curl -X POST http://localhost:5000/feedback \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg_abc123",
    "rating": 1,
    "category": "helpful",
    "comment": "Great suggestion!"
  }'
```

Response:
```json
{
  "status": "success",
  "feedback_id": "fbk_xyz789"
}
```

## Analytics & Monitoring

The `FeedbackManager` includes methods for analyzing feedback:

```python
# Get feedback for a specific message
feedback_manager.get_feedback_for_message("msg_abc123")

# Get feedback from a specific user
feedback_manager.get_feedback_for_user("user_456")

# Get overall summary
summary = feedback_manager.get_feedback_summary()
# Returns: {
#   "total_feedback": 42,
#   "average_rating": 0.85,
#   "category_breakdown": {"helpful": 30, "hallucination": 5, ...},
#   "recent_24h": 7
# }
```

## Next Steps

### For Frontend Integration
1. Capture the `message_id` from each `/chat` response
2. Add a feedback button/form for each message
3. Submit feedback via the `/feedback` endpoint
4. Show confirmation when feedback is received

### For Analytics
1. Build a dashboard to view feedback summaries
2. Create alerts for low ratings or specific categories
3. Track feedback trends over time
4. Identify problem areas for improvement

### For Product Development
1. Review feedback regularly
2. Identify patterns in user issues
3. Prioritize fixes based on feedback volume
4. Create feature requests based on suggestions
5. Monitor success of improvements through feedback

## Testing the Feedback Loop

The Swagger UI at `http://localhost:5000/api/docs` includes interactive testing for both endpoints:

1. Visit `http://localhost:5000/api/docs`
2. Try the `/chat` endpoint (need valid token)
3. Copy the `message_id` from the response
4. Try the `/feedback` endpoint with that `message_id`
5. View database records in `data/feedback.db`

---

**Created:** November 13, 2025
**System:** Caudex Pro AI Router (The Brain)
**Status:** ✅ Feedback loop fully operational

