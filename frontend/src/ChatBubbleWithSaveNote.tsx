/**
 * Example Chat Bubble Component with Save as Note Feature
 * This demonstrates how to integrate the new save-as-note functionality
 */

import React, { useState } from 'react';
import { ChatResponse, saveMessageAsNote, postFeedback } from './api-client';

interface ChatBubbleProps {
  message: ChatResponse;
  onFeedbackSubmitted?: (feedbackId: string) => void;
  onNoteSaved?: (notePath: string) => void;
}

export const ChatBubble: React.FC<ChatBubbleProps> = ({
  message,
  onFeedbackSubmitted,
  onNoteSaved
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [noteStatus, setNoteStatus] = useState<'idle' | 'success' | 'error'>('idle');

  const handleFeedback = async (rating: number) => {
    setIsLoading(true);
    try {
      const response = await postFeedback({
        message_id: message.messageId,
        rating,
        category: 'general'
      });
      
      setFeedbackStatus('success');
      onFeedbackSubmitted?.(response.feedback_id);
      
      // Clear status after 3 seconds
      setTimeout(() => setFeedbackStatus('idle'), 3000);
    } catch (error) {
      console.error('Failed to submit feedback', error);
      setFeedbackStatus('error');
      setTimeout(() => setFeedbackStatus('idle'), 3000);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveAsNote = async () => {
    setIsLoading(true);
    try {
      const response = await saveMessageAsNote(message.messageId);
      
      setNoteStatus('success');
      onNoteSaved?.(response.note_path);
      
      // Clear status after 3 seconds
      setTimeout(() => setNoteStatus('idle'), 3000);
    } catch (error) {
      console.error('Failed to save note', error);
      setNoteStatus('error');
      setTimeout(() => setNoteStatus('idle'), 3000);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-bubble ai-response" data-message-id={message.messageId}>
      {/* Main message content */}
      <div className="bubble-content">
        <p>{message.response}</p>
        {message.cost > 0 && (
          <div className="message-metadata">
            <small>Cost: ${message.cost.toFixed(4)}</small>
            {message.downgraded && (
              <span className="downgrade-badge">Limited Response</span>
            )}
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="bubble-actions">
        {/* Feedback buttons */}
        <div className="feedback-group">
          <button
            className="action-btn feedback-btn positive"
            title="This response was helpful"
            onClick={() => handleFeedback(1)}
            disabled={isLoading}
            aria-label="Mark as helpful"
          >
            👍
          </button>
          <button
            className="action-btn feedback-btn negative"
            title="This response wasn't helpful"
            onClick={() => handleFeedback(-1)}
            disabled={isLoading}
            aria-label="Mark as not helpful"
          >
            👎
          </button>
        </div>

        {/* Save as Note button */}
        <button
          className="action-btn save-note-btn"
          title="Save this response as a note in your knowledge base"
          onClick={handleSaveAsNote}
          disabled={isLoading}
          aria-label="Save as note"
        >
          🔖
        </button>

        {/* Status indicators */}
        {feedbackStatus === 'success' && (
          <span className="status-indicator success">Feedback saved</span>
        )}
        {feedbackStatus === 'error' && (
          <span className="status-indicator error">Failed to save feedback</span>
        )}

        {noteStatus === 'success' && (
          <span className="status-indicator success">Note saved!</span>
        )}
        {noteStatus === 'error' && (
          <span className="status-indicator error">Failed to save note</span>
        )}
      </div>
    </div>
  );
};

export default ChatBubble;
