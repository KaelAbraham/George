/**
 * High-level API functions for easier usage
 * These wrap the CaudexAPIClient for convenience
 */

import CaudexAPIClient from './client';
import {
  ChatRequest,
  ChatResponse,
  JobStatus,
  JobsList,
  WikiGenerationResponse,
  CostSummary
} from './models';

let client: CaudexAPIClient | null = null;

/**
 * Initialize the global API client
 */
export function initializeClient(baseURL?: string): CaudexAPIClient {
  client = new CaudexAPIClient(baseURL);
  return client;
}

/**
 * Get the global API client instance
 */
export function getClient(): CaudexAPIClient {
  if (!client) {
    client = new CaudexAPIClient();
  }
  return client;
}

/**
 * Post a chat query
 */
export async function postChat(
  query: string,
  projectId: string
): Promise<ChatResponse> {
  return getClient().postChat(query, projectId);
}

/**
 * Get job status
 */
export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return getClient().getJobStatus(jobId);
}

/**
 * Get project jobs
 */
export async function getProjectJobs(projectId: string): Promise<JobsList> {
  return getClient().getProjectJobs(projectId);
}

/**
 * Generate wiki for project
 */
export async function generateWiki(
  projectId: string
): Promise<WikiGenerationResponse> {
  return getClient().generateWiki(projectId);
}

/**
 * Get admin costs
 */
export async function getAdminCosts(): Promise<CostSummary> {
  return getClient().getAdminCosts();
}

export { CaudexAPIClient };
