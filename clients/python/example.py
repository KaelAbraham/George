"""
Example usage of the Caudex Pro AI Router Python client
"""
from caudex_client import CaudexAPIClient

def main():
    # Initialize the client
    with CaudexAPIClient() as client:
        try:
            # Example 1: Chat query
            print("\n=== Chat Query ===")
            response = client.post_chat(
                query="What is the purpose of this project?",
                project_id="project-123"
            )
            print(f"Response: {response.response}")
            print(f"Intent: {response.intent}")
            print(f"Cost: {response.cost}")
            print(f"Downgraded: {response.downgraded}")
            
            # Example 2: Get job status
            print("\n=== Get Job Status ===")
            job_status = client.get_job_status("job-123")
            print(f"Job ID: {job_status.job_id}")
            print(f"Status: {job_status.status}")
            print(f"Type: {job_status.job_type}")
            
            # Example 3: Get project jobs
            print("\n=== Get Project Jobs ===")
            jobs_list = client.get_project_jobs("project-123")
            print(f"Project: {jobs_list.project_id}")
            print(f"Number of jobs: {len(jobs_list.jobs)}")
            for job in jobs_list.jobs:
                print(f"  - {job.job_id}: {job.status}")
            
            # Example 4: Admin costs
            print("\n=== Admin Costs ===")
            costs = client.get_admin_costs()
            print(f"Total tokens: {costs.total_tokens}")
            print(f"Total cost: ${costs.total_cost}")
            for client_name, metrics in costs.clients.items():
                print(f"  {client_name}: {metrics}")
        
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
