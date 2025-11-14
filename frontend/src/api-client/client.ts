/**
 * Auto-generated API Client for Caudex Pro AI Router
 * Uses axios for HTTP requests
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import {
  ChatRequest,
  ChatResponse,
  FeedbackRequest,
  FeedbackResponse,
  SaveNoteResponse,
  BookmarkRequest,
  BookmarkResponse,
  ProjectBookmarksResponse,
  JobStatus,
  JobsList,
  WikiGenerationResponse,
  CostSummary
} from './models';

export class CaudexAPIClient {
  private axiosInstance: AxiosInstance;
  private baseURL: string;

  constructor(baseURL: string = 'http://localhost:5001', timeout: number = 30000) {
    this.baseURL = baseURL.replace(/\/$/, '');
    this.axiosInstance = axios.create({
      baseURL: this.baseURL,
      timeout
    });
  }

  // Chat Endpoints

  /**
   * Post a chat query to the AI router
   * @param query The user's query
   * @param projectId Project ID
   * @returns ChatResponse with AI response and metadata
   */
  async postChat(query: string, projectId: string): Promise<ChatResponse> {
    const payload: ChatRequest = { query, project_id: projectId };
    try {
      const response = await this.axiosInstance.post<ChatResponse>('/chat', payload);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Submit feedback for a chat message
   * @param feedback The feedback request containing message_id, rating, category, comment
   * @returns FeedbackResponse with status and feedback_id
   */
  async postFeedback(feedback: FeedbackRequest): Promise<FeedbackResponse> {
    try {
      const response = await this.axiosInstance.post<FeedbackResponse>(
        '/feedback',
        feedback
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Save a chat message as a note in the knowledge base
   * @param messageId The message ID to save as a note
   * @returns SaveNoteResponse with status and note path
   */
  async saveMessageAsNote(messageId: string): Promise<SaveNoteResponse> {
    try {
      const response = await this.axiosInstance.post<SaveNoteResponse>(
        `/chat/${messageId}/save_as_note`
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Bookmark a chat message for later reference
   * @param messageId The message ID to bookmark
   * @param isBookmarked True to bookmark, false to unbookmark
   * @returns BookmarkResponse with updated status
   */
  async toggleBookmark(messageId: string, isBookmarked: boolean): Promise<BookmarkResponse> {
    try {
      const payload: BookmarkRequest = { is_bookmarked: isBookmarked };
      const response = await this.axiosInstance.post<BookmarkResponse>(
        `/chat/${messageId}/bookmark`,
        payload
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Get all bookmarked messages for a project
   * @param projectId The project ID
   * @returns ProjectBookmarksResponse with list of bookmarked messages
   */
  async getProjectBookmarks(projectId: string): Promise<ProjectBookmarksResponse> {
    try {
      const response = await this.axiosInstance.get<ProjectBookmarksResponse>(
        `/project/${projectId}/bookmarks`
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // Job Endpoints

  /**
   * Get the status of a specific job
   * @param jobId The job ID
   * @returns JobStatus with job information
   */
  async getJobStatus(jobId: string): Promise<JobStatus> {
    try {
      const response = await this.axiosInstance.get<JobStatus>(`/jobs/${jobId}`);
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Get all jobs for a specific project
   * @param projectId The project ID
   * @returns JobsList containing all jobs for the project
   */
  async getProjectJobs(projectId: string): Promise<JobsList> {
    try {
      const response = await this.axiosInstance.get<JobsList>(
        `/project/${projectId}/jobs`
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Generate wiki documentation for a project (async)
   * @param projectId The project ID
   * @returns WikiGenerationResponse with job info
   */
  async generateWiki(projectId: string): Promise<WikiGenerationResponse> {
    try {
      const response = await this.axiosInstance.post<WikiGenerationResponse>(
        `/project/${projectId}/generate_wiki`
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // Admin Endpoints

  /**
   * Get cost summary for all LLM clients (requires admin access)
   * @returns CostSummary with aggregate cost information
   */
  async getAdminCosts(): Promise<CostSummary> {
    try {
      const response = await this.axiosInstance.get<CostSummary>('/admin/costs');
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // Utility methods

  /**
   * Handle axios errors and convert to more user-friendly format
   */
  private handleError(error: any): Error {
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError;
      if (axiosError.response) {
        return new Error(
          `API Error ${axiosError.response.status}: ${
            (axiosError.response.data as any)?.message ||
            axiosError.response.statusText
          }`
        );
      } else if (axiosError.request) {
        return new Error(`No response from server: ${axiosError.message}`);
      }
    }
    return error instanceof Error ? error : new Error(String(error));
  }

  /**
   * Get the configured base URL
   */
  getBaseURL(): string {
    return this.baseURL;
  }

  /**
   * Update the base URL
   */
  setBaseURL(baseURL: string): void {
    this.baseURL = baseURL.replace(/\/$/, '');
    this.axiosInstance.defaults.baseURL = this.baseURL;
  }
}

export default CaudexAPIClient;

