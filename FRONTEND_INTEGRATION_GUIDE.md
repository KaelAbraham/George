# Save as Note - Frontend Integration Guide

## Quick Start

### 1. Import the API Functions

```typescript
import { 
  saveMessageAsNote, 
  postFeedback,
  SaveNoteResponse,
  FeedbackRequest 
} from './api-client';
```

### 2. Add the Button to Your Chat Bubble

```jsx
<button 
  onClick={() => handleSaveAsNote(message.messageId)}
  className="btn-save-note"
  title="Save this response as a note in your knowledge base"
>
  🔖 Save as Note
</button>
```

### 3. Implement the Handler

```typescript
const handleSaveAsNote = async (messageId: string) => {
  try {
    const response = await saveMessageAsNote(messageId);
    
    // Show success message
    showNotification({
      type: 'success',
      message: `Note saved! 📝`,
      description: `Saved to ${response.note_path}`
    });
    
  } catch (error) {
    showNotification({
      type: 'error',
      message: 'Failed to save note',
      description: error.message
    });
  }
};
```

## Key Points

### Message ID
Every chat response now includes a unique `messageId`:
```typescript
const response = await postChat('Your query', projectId);
console.log(response.messageId); // "msg_12345678-1234-1234-1234-123456789abc"
```

### Feedback Integration
Both feedback and save-as-note use the same `messageId`:
```typescript
// User can both rate AND save the same response
await postFeedback({
  message_id: response.messageId,
  rating: 1
});

await saveMessageAsNote(response.messageId);
```

### Error Handling
Common errors:
- `401` - User not authenticated (check token)
- `404` - Message not found or access denied
- `500` - Microservice failure (filesystem or Chroma down)

```typescript
try {
  await saveMessageAsNote(messageId);
} catch (error) {
  if (error.message.includes('401')) {
    // Re-authenticate user
  } else if (error.message.includes('404')) {
    // Message no longer available
  } else if (error.message.includes('500')) {
    // Temporary service issue
  }
}
```

## UI/UX Recommendations

### Button Placement
Place the save button alongside feedback buttons:
```
👍 👎 🔖
```

### Visual Feedback
Show status while saving:
```jsx
const [isSaving, setIsSaving] = useState(false);

<button 
  onClick={() => handleSaveAsNote(messageId)}
  disabled={isSaving}
>
  {isSaving ? '⏳' : '🔖'}
</button>
```

### Toast Notifications
Use a toast system for feedback:
```typescript
const response = await saveMessageAsNote(messageId);
if (response.status === 'success') {
  toast.success('✅ Saved as note', {
    duration: 3000,
    action: {
      label: 'View',
      onClick: () => viewNote(response.note_path)
    }
  });
}
```

### Accessibility
```jsx
<button
  aria-label="Save this response as a note"
  title="Save response to knowledge base"
  onClick={handleSaveAsNote}
>
  🔖
</button>
```

## Complete Example Component

```typescript
import React, { useState } from 'react';
import { ChatResponse, saveMessageAsNote } from './api-client';
import Toast from './Toast'; // Your toast component

interface ChatMessageProps {
  message: ChatResponse;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const [isSaving, setIsSaving] = useState(false);
  const [showToast, setShowToast] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  const handleSaveAsNote = async () => {
    setIsSaving(true);
    try {
      const response = await saveMessageAsNote(message.messageId);
      setShowToast({
        type: 'success',
        message: `Note saved to ${response.note_path}`
      });
    } catch (error) {
      setShowToast({
        type: 'error',
        message: `Failed to save: ${error.message}`
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
      <div className="message">
        <div className="content">
          {message.response}
        </div>
        
        <div className="actions">
          <button
            onClick={handleSaveAsNote}
            disabled={isSaving}
            title="Save this response as a note"
            aria-label="Save as note"
          >
            {isSaving ? '⏳ Saving...' : '🔖 Save'}
          </button>
        </div>
      </div>
      
      {showToast && (
        <Toast
          type={showToast.type}
          message={showToast.message}
          onClose={() => setShowToast(null)}
        />
      )}
    </>
  );
};
```

## API Reference

### `saveMessageAsNote(messageId: string): Promise<SaveNoteResponse>`

Saves a chat response as a markdown note in the project's knowledge base.

**Parameters:**
- `messageId` (string) - The unique message ID from the chat response

**Returns:**
```typescript
{
  status: 'success' | 'partial_success',
  note_path: string,           // e.g., "notes/note_msg_abc123.md"
  ingest_status: 'success' | 'warning'
}
```

**Throws:**
- `Error` - If authentication fails, message not found, or services unavailable

**Example:**
```typescript
const result = await saveMessageAsNote('msg_abc123');
console.log(result.note_path); // "notes/note_msg_abc123.md"
```

### `postFeedback(feedback: FeedbackRequest): Promise<FeedbackResponse>`

Submits feedback for a chat message.

**Parameters:**
```typescript
{
  message_id: string;           // Required
  rating: number;               // Required: 1 (helpful) or -1 (not helpful)
  category?: string;            // Optional: 'accurate', 'helpful', 'unclear', etc.
  comment?: string;             // Optional: Free-form feedback text
}
```

**Returns:**
```typescript
{
  status: 'success',
  feedback_id: string          // e.g., "fbk_xyz789"
}
```

**Example:**
```typescript
const feedback = await postFeedback({
  message_id: 'msg_abc123',
  rating: 1,
  category: 'accurate',
  comment: 'This perfectly answered my question!'
});
```

## Testing

### Test locally with the example component:

```bash
# 1. Start the backend
cd backend
python app.py

# 2. In your React app, import and use the component:
import ChatBubbleWithSaveNote from './ChatBubbleWithSaveNote';

# 3. Create a test message:
const testMessage: ChatResponse = {
  messageId: 'msg_test_123',
  response: 'This is a test response.',
  intent: 'general',
  cost: 0.001,
  downgraded: false,
  balance: 10.5
};

<ChatBubbleWithSaveNote message={testMessage} />
```

## Troubleshooting

### Button click doesn't work
- Check if `messageId` is present in the message object
- Verify authentication token is set in the axios instance
- Check browser console for errors

### "Failed to save note" error
- Verify filesystem service is running on the configured port
- Verify Chroma service is running
- Check backend logs for detailed error

### Note not appearing in knowledge base
- Check that Chroma ingest completed (check `ingest_status`)
- Verify the `project_id` was correctly associated
- Note should be searchable via semantic search on Chroma

## Next Steps

1. ✅ Copy `ChatBubbleWithSaveNote.tsx` as a template
2. ✅ Integrate into your chat UI component
3. ✅ Add toast notifications for user feedback
4. ✅ Test with the backend
5. ✅ Deploy to production

For questions, check `SAVE_AS_NOTE_FEATURE.md` for full technical documentation.
