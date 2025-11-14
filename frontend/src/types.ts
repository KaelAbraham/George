export interface User {
  uid: string;
  email: string;
  role: 'admin' | 'guest';
  [key: string]: any;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  [key: string]: any;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

export interface AuthPayload {
  email: string;
  password: string;
}

export interface AuthResponse {
  success: boolean;
  user?: User;
  error?: string;
}
