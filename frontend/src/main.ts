// Import the API client from your auto-generated client
import { initializeClient, postChat } from './api-client/api';

// --- 1. Configure the API Client ---
// Tell the client where your backend is running
initializeClient('http://localhost:5001');

// --- 2. Prepare the Request ---
const testQuery = "Hello, George! Is this bridge working?";
const testProjectId = "p-hello-world";

// --- 3. Make the API Call ---
async function testApiBridge() {
    const app = document.getElementById('app');
    if (!app) return;

    app.innerHTML = "<p>Testing API bridge...</p>";
    console.log("Sending request:", { query: testQuery, project_id: testProjectId });

    try {
        // This is the auto-generated convenience function!
        // It calls POST /chat with your request
        const response = await postChat(testQuery, testProjectId);
        
        // --- 4. Show Success! ---
        console.log("SUCCESS! Server responded:", response);
        app.innerHTML = `
            <div style="font-family: Arial, sans-serif; padding: 20px; background: #f0f8ff; border-radius: 10px;">
                <h2 style="color: #4caf50;">✅ Bridge is LIVE!</h2>
                <p><strong>Query sent:</strong> <code>${testQuery}</code></p>
                <p><strong>Response:</strong> <code>${response.response}</code></p>
                <p><strong>Intent detected:</strong> <code>${response.intent}</code></p>
                <p><strong>Cost:</strong> <code>$${response.cost}</code></p>
                <details>
                    <summary>Full Response</summary>
                    <pre style="background: white; padding: 10px; border-radius: 5px; overflow-x: auto;">${JSON.stringify(response, null, 2)}</pre>
                </details>
            </div>
        `;

    } catch (error) {
        // --- 5. Show Failure ---
        const errorMessage = error instanceof Error ? error.message : String(error);
        console.error("FAILED to call API:", error);
        app.innerHTML = `
            <div style="font-family: Arial, sans-serif; padding: 20px; background: #ffebee; border-radius: 10px;">
                <h2 style="color: #f44336;">❌ Bridge FAILED</h2>
                <p>Could not connect to the backend.</p>
                <p><strong>Troubleshooting:</strong></p>
                <ul>
                    <li>Is your Python backend running? <code>python backend/app.py</code></li>
                    <li>Did you add CORS to the backend? (flask_cors import and CORS(app))</li>
                    <li>Is the backend running on port 5001?</li>
                    <li>Check browser console for more details</li>
                </ul>
                <details>
                    <summary>Error Details</summary>
                    <pre style="background: white; padding: 10px; border-radius: 5px; color: #f44336; overflow-x: auto;">${errorMessage}</pre>
                </details>
            </div>
        `;
    }
}

// Run the test when the DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', testApiBridge);
} else {
    testApiBridge();
}
