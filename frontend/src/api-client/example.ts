/**
 * Example usage of the Caudex Pro AI Router TypeScript Client
 */

import {
  initializeClient,
  postChat,
  getJobStatus,
  getProjectJobs,
  generateWiki,
  getAdminCosts
} from './index';

async function main() {
  // Initialize client
  initializeClient('http://localhost:5001');

  try {
    // Example 1: Post a chat query
    console.log('\n=== Chat Query ===');
    const chatResponse = await postChat(
      'What is the purpose of this project?',
      'project-123'
    );
    console.log('Response:', chatResponse.response);
    console.log('Intent:', chatResponse.intent);
    console.log('Cost:', chatResponse.cost);

    // Example 2: Get job status
    console.log('\n=== Get Job Status ===');
    const jobStatus = await getJobStatus('job-123');
    console.log('Job ID:', jobStatus.job_id);
    console.log('Status:', jobStatus.status);
    console.log('Type:', jobStatus.job_type);

    // Example 3: Get project jobs
    console.log('\n=== Get Project Jobs ===');
    const jobsList = await getProjectJobs('project-123');
    console.log('Project:', jobsList.project_id);
    console.log('Number of jobs:', jobsList.jobs.length);
    jobsList.jobs.forEach((job) => {
      console.log(`  - ${job.job_id}: ${job.status}`);
    });

    // Example 4: Generate wiki
    console.log('\n=== Generate Wiki ===');
    const wikiResponse = await generateWiki('project-123');
    console.log('Message:', wikiResponse.message);
    console.log('Job ID:', wikiResponse.job_id);

    // Example 5: Get admin costs
    console.log('\n=== Admin Costs ===');
    const costs = await getAdminCosts();
    console.log('Total tokens:', costs.total_tokens);
    console.log('Total cost:', costs.total_cost);
    for (const [clientName, metrics] of Object.entries(costs.clients)) {
      console.log(`  ${clientName}:`, metrics);
    }
  } catch (error) {
    console.error('Error:', error);
  }
}

// Run example if this file is executed directly
if (require.main === module) {
  main().catch(console.error);
}

export { main };
