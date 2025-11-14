/**
 * Auto-generated data models from OpenAPI spec
 */

export interface ChatRequest {
  query: string;
  project_id: string;
}

export interface ChatResponse {
  messageId: string;
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

export interface BookmarkRequest {
  is_bookmarked: boolean;
}

export interface BookmarkResponse {
  status: string;
  message_id: string;
  is_bookmarked: boolean;
}

export interface BookmarkedMessage {
  message_id: string;
  user_query: string;
  ai_response: string;
  timestamp: string;
  id: number;
}

export interface ProjectBookmarksResponse {
  bookmarks: BookmarkedMessage[];
}

export interface JobStatus {
  job_id: string;
  project_id: string;
  user_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  job_type: string;
  created_at: string;
  result?: Record<string, any> | null;
}

export interface JobsList {
  project_id: string;
  jobs: JobStatus[];
}

export interface WikiGenerationResponse {
  message: string;
  job_id: string;
  status_url: string;
}

export interface CostSummary {
  total_tokens: number;
  total_cost: number;
  clients: Record<string, { tokens: number; cost: number }>;
}