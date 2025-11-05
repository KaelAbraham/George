"""Main application file for the git server."""
from flask import Flask, request, jsonify
import git
import os

app = Flask(__name__)

# Configuration
PROJECTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects')
app.config['PROJECTS_FOLDER'] = PROJECTS_FOLDER

# Ensure directories exist
os.makedirs(app.config['PROJECTS_FOLDER'], exist_ok=True)

@app.route('/snapshot/<project_id>', methods=['POST'])
def snapshot(project_id):
    project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
    
    if not os.path.isdir(project_path):
        os.makedirs(project_path)
        repo = git.Repo.init(project_path)
    else:
        try:
            repo = git.Repo(project_path)
        except git.exc.InvalidGitRepositoryError:
            repo = git.Repo.init(project_path)
        
    # For simplicity, we'll just commit all changes.
    # In a real application, you would handle specific files.
    repo.git.add(A=True)
    
    try:
        commit = repo.index.commit(f"Snapshot for project {project_id}")
        return jsonify({'message': 'Snapshot created successfully', 'commit_hash': commit.hexsha}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/history/<project_id>', methods=['GET'])
def history(project_id):
    project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
    
    if not os.path.isdir(project_path):
        return jsonify({'error': 'Project not found'}), 404
        
    repo = git.Repo(project_path)
    commits = list(repo.iter_commits())
    
    return jsonify([{'commit_hash': c.hexsha, 'message': c.message, 'date': c.committed_datetime.isoformat()} for c in commits])

if __name__ == '__main__':
    app.run(debug=True, port=5003)
