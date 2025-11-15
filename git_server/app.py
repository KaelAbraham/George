"""Main application file for the git server."""
from flask import Flask, request, jsonify
import git
import os
import tempfile
import shutil
from datetime import datetime

app = Flask(__name__)

# Configuration
PROJECTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects')
TEMP_CHECKOUTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_checkouts')
app.config['PROJECTS_FOLDER'] = PROJECTS_FOLDER
app.config['TEMP_CHECKOUTS'] = TEMP_CHECKOUTS

# Ensure directories exist
os.makedirs(app.config['PROJECTS_FOLDER'], exist_ok=True)
os.makedirs(app.config['TEMP_CHECKOUTS'], exist_ok=True)

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
        app.logger.error(f"Failed to create snapshot: {e}", exc_info=True)
        return jsonify({'error': 'Failed to create snapshot'}), 500

@app.route('/history/<project_id>', methods=['GET'])
def history(project_id):
    """
    Get the commit history for a project.
    
    Returns a list of commits with hash, message, and timestamp.
    """
    project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
    
    if not os.path.isdir(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    try:
        repo = git.Repo(project_path)
        commits = list(repo.iter_commits())
        
        history_data = []
        for c in commits:
            history_data.append({
                'commit_hash': c.hexsha,
                'message': c.message.strip(),
                'author': c.author.name if c.author else 'Unknown',
                'date': c.committed_datetime.isoformat(),
                'short_hash': c.hexsha[:7]
            })
        
        return jsonify({
            'project_id': project_id,
            'commits': history_data,
            'total_commits': len(history_data)
        }), 200
        
    except git.exc.InvalidGitRepositoryError:
        return jsonify({'error': 'Project has no git history'}), 404
    except Exception as e:
        app.logger.error(f"Failed to get history: {e}", exc_info=True)
        return jsonify({'error': 'Failed to get history'}), 500


@app.route('/checkout/<project_id>/<commit_hash>', methods=['GET'])
def checkout(project_id, commit_hash):
    """
    Restore a specific version of the manuscript to a temp folder.
    
    Args:
        project_id: The project identifier
        commit_hash: The commit hash (full or short) to checkout
        
    Returns:
        A JSON response with the temp folder path and file list
    """
    project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
    
    if not os.path.isdir(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    try:
        repo = git.Repo(project_path)
        
        # Verify the commit exists
        try:
            commit = repo.commit(commit_hash)
        except git.exc.BadName:
            return jsonify({'error': f'Commit hash "{commit_hash}" not found'}), 404
        
        # Create a unique temp folder for this checkout
        checkout_id = f"{project_id}_{commit_hash[:7]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        temp_folder = os.path.join(app.config['TEMP_CHECKOUTS'], checkout_id)
        os.makedirs(temp_folder, exist_ok=True)
        
        # Checkout the specific commit to the temp folder
        # We do this by copying files from the commit to the temp folder
        try:
            # Create a temporary work tree
            repo.git.worktree('add', '--detach', temp_folder, commit_hash)
            
            # Get the list of files in this commit
            files = []
            for item in commit.tree.traverse():
                if item.type == 'blob':  # It's a file
                    files.append(item.path)
            
            return jsonify({
                'project_id': project_id,
                'commit_hash': commit.hexsha,
                'short_hash': commit.hexsha[:7],
                'commit_message': commit.message.strip(),
                'author': commit.author.name if commit.author else 'Unknown',
                'committed_date': commit.committed_datetime.isoformat(),
                'temp_folder': temp_folder,
                'checkout_id': checkout_id,
                'files': files,
                'file_count': len(files)
            }), 200
            
        except Exception as e:
            app.logger.error(f"Failed to create work tree: {e}")
            # Fallback: copy the files manually
            # First, extract the tree contents to temp folder
            for item in commit.tree.traverse():
                if item.type == 'blob':  # It's a file
                    file_path = os.path.join(temp_folder, item.path)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, 'wb') as f:
                        f.write(item.data_stream.read())
            
            files = []
            for root, dirs, filenames in os.walk(temp_folder):
                for filename in filenames:
                    file_path = os.path.relpath(os.path.join(root, filename), temp_folder)
                    files.append(file_path)
            
            return jsonify({
                'project_id': project_id,
                'commit_hash': commit.hexsha,
                'short_hash': commit.hexsha[:7],
                'commit_message': commit.message.strip(),
                'author': commit.author.name if commit.author else 'Unknown',
                'committed_date': commit.committed_datetime.isoformat(),
                'temp_folder': temp_folder,
                'checkout_id': checkout_id,
                'files': files,
                'file_count': len(files)
            }), 200
    
    except git.exc.InvalidGitRepositoryError:
        return jsonify({'error': 'Project has no git history'}), 404
    except Exception as e:
        app.logger.error(f"Checkout failed: {e}", exc_info=True)
        return jsonify({'error': 'Checkout failed'}), 500


@app.route('/cleanup/<checkout_id>', methods=['DELETE'])
def cleanup(checkout_id):
    """
    Clean up a temporary checkout folder.
    
    Args:
        checkout_id: The checkout ID returned from the checkout endpoint
        
    Returns:
        A JSON response confirming deletion
    """
    temp_folder = os.path.join(app.config['TEMP_CHECKOUTS'], checkout_id)
    
    if not os.path.isdir(temp_folder):
        return jsonify({'error': 'Checkout not found'}), 404
    
    try:
        shutil.rmtree(temp_folder)
        return jsonify({'message': f'Cleanup successful for checkout "{checkout_id}"'}), 200
    except Exception as e:
        app.logger.error(f"Cleanup failed: {e}", exc_info=True)
        return jsonify({'error': 'Cleanup failed'}), 500


@app.route('/get_file/<project_id>/<path:file_path>', methods=['GET'])
def get_file(project_id, file_path):
    """
    Get the contents of a file from a specific commit (or current HEAD).
    
    Query params:
        commit_hash: (optional) If provided, reads from that commit; otherwise reads from HEAD
    """
    commit_hash = request.args.get('commit_hash', 'HEAD')
    project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
    
    if not os.path.isdir(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    try:
        repo = git.Repo(project_path)
        commit = repo.commit(commit_hash)
        
        # Navigate the tree to find the file
        try:
            file_obj = commit.tree / file_path
            if file_obj.type != 'blob':
                return jsonify({'error': 'Not a file'}), 400
            
            content = file_obj.data_stream.read().decode('utf-8', errors='replace')
            
            return jsonify({
                'project_id': project_id,
                'file_path': file_path,
                'commit_hash': commit.hexsha,
                'content': content,
                'size': len(content)
            }), 200
            
        except KeyError:
            return jsonify({'error': f'File "{file_path}" not found in this commit'}), 404
    
    except git.exc.BadName:
        return jsonify({'error': f'Commit "{commit_hash}" not found'}), 404
    except git.exc.InvalidGitRepositoryError:
        return jsonify({'error': 'Project has no git history'}), 404
    except Exception as e:
        app.logger.error(f"File retrieval failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    import os
    if os.getenv('FLASK_ENV') == 'development':
        app.run(debug=True, port=6005)
    else:
        print("Use gunicorn for production: gunicorn -w 4 -b 0.0.0.0:6005 git_server.app:app")
