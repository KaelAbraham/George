# Caudex Pro AI Router TypeScript Client

Auto-generated type-safe TypeScript client for the Caudex Pro AI Router API using axios.

## Installation

```bash
npm install axios
```

## Quick Start

```typescript
import { initializeClient, postChat } from './api-client';

// Initialize client
initializeClient('http://localhost:5001');

// Post a chat query
const response = await postChat(
  'What is the project structure?',
  'my-project'
);
console.log(response.response);
```

## API Reference

### Initialize Client

```typescript
import { initializeClient, getClient } from './api-client';

// Auto-initialize with custom base URL
initializeClient('http://localhost:5001');

// Or get default client instance
const client = getClient();
client.setBaseURL('http://api.example.com');
```

### Chat Endpoint

```typescript
import { postChat } from './api-client';

const response = await postChat(
  query: string,
  projectId: string
): Promise<ChatResponse>
```

### Job Management

```typescript
import { getJobStatus, getProjectJobs, generateWiki } from './api-client';

// Get single job status
const status: JobStatus = await getJobStatus(jobId);

// Get all project jobs
const jobs: JobsList = await getProjectJobs(projectId);

// Generate wiki (async, returns 202)
const result: WikiGenerationResponse = await generateWiki(projectId);
```

### Admin Endpoints

```typescript
import { getAdminCosts } from './api-client';

// Get cost summary (requires admin access)
const costs: CostSummary = await getAdminCosts();
```

## Data Models

All models are fully typed with TypeScript interfaces:

- `ChatRequest` - Request payload for chat endpoint
- `ChatResponse` - Response from chat endpoint
- `JobStatus` - Individual job information
- `JobsList` - Collection of jobs for a project
- `WikiGenerationResponse` - Async wiki generation response
- `CostSummary` - Cost aggregation across LLM clients

## Error Handling

```typescript
import { postChat } from './api-client';

try {
  const response = await postChat(...);
} catch (error) {
  console.error('API error:', error.message);
}
```

All errors are converted to standard JavaScript `Error` objects with descriptive messages.

## Usage Methods

### Method 1: Using convenience functions (recommended)

```typescript
import { postChat, getJobStatus } from './api-client';

const response = await postChat(query, projectId);
const status = await getJobStatus(jobId);
```

### Method 2: Using the client directly

```typescript
import { CaudexAPIClient } from './api-client';

const client = new CaudexAPIClient('http://localhost:5001');
const response = await client.postChat(query, projectId);
```

### Method 3: In React components

```typescript
import { useEffect, useState } from 'react';
import { getProjectJobs } from '@/api-client';

export function ProjectJobs({ projectId }: { projectId: string }) {
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    getProjectJobs(projectId)
      .then((data) => setJobs(data.jobs))
      .catch(console.error);
  }, [projectId]);

  return (
    <ul>
      {jobs.map((job) => (
        <li key={job.job_id}>{job.job_id}: {job.status}</li>
      ))}
    </ul>
  );
}
```

## Generated

- **Generated**: November 13, 2025
- **From**: api_spec.json (OpenAPI 3.0.2)
- **Generator**: TypeScript client generator
- **HTTP Client**: axios

## File Structure

```
frontend/src/api-client/
  ├── models.ts      # TypeScript interfaces for all models
  ├── client.ts      # CaudexAPIClient class using axios
  ├── api.ts         # Convenience functions
  ├── example.ts     # Usage examples
  ├── index.ts       # Main exports
  └── README.md      # This file
```

## Requirements

- TypeScript 4.0+
- axios 0.27.0+
- Node.js 14+

## Integration with React

Add to your React project's API utilities:

```typescript
// src/api/index.ts
export * from '../../api-client';
```

Then use anywhere in your components:

```typescript
import { postChat } from '@/api';
```
