"""Project management utilities for manuscript organization and asset tracking."""
import os
import json
import shutil
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
# Set up logger
logger = logging.getLogger(__name__)
class ProjectError(Exception):
    """Custom exception for project management errors."""
    pass
class ProjectManager:
    """Project management utilities for manuscript organization and asset tracking."""
    def __init__(self, base_dir: str = "/app/local_story_ai_1423"):
        """Initialize the project manager.
        Args:
            base_dir (str): Base directory for projects
        """
        self.base_dir = base_dir
        self.projects_dir = os.path.join(base_dir, "projects")
        # Create projects directory if it doesn't exist
        os.makedirs(self.projects_dir, exist_ok=True)
    def create_project(self, project_name: str, author: str = "", 
                      description: str = "") -> str:
        """
        Create a new project with the required directory structure.
        Args:
            project_name (str): Name of the project
            author (str): Author of the project
            description (str): Description of the project
        Returns:
            str: Path to the created project directory
        """
        # Validate project name
        if not project_name or not project_name.strip():
            raise ProjectError("Project name cannot be empty")
        # Create project directory
        project_dir = os.path.join(self.projects_dir, project_name)
        if os.path.exists(project_dir):
            raise ProjectError(f"Project '{project_name}' already exists")
        try:
            os.makedirs(project_dir)
            # Create project subdirectories
            subdirs = [
                "manuscripts",
                "processed",
                "entities",
                "knowledge_base",
                "exports",
                "backups"
            ]
            for subdir in subdirs:
                os.makedirs(os.path.join(project_dir, subdir))
            # Create project metadata file
            metadata = {
                "project_name": project_name,
                "author": author,
                "description": description,
                "created_at": datetime.now().isoformat(),
                "last_modified": datetime.now().isoformat(),
                "manuscripts": [],
                "processing_status": "created"
            }
            metadata_path = os.path.join(project_dir, "project.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"Project '{project_name}' created successfully at {project_dir}")
            return project_dir
        except Exception as e:
            # Clean up if creation failed
            if os.path.exists(project_dir):
                shutil.rmtree(project_dir)
            raise ProjectError(f"Failed to create project: {e}")
    def load_project(self, project_name: str) -> Dict[str, Any]:
        """
        Load an existing project.
        Args:
            project_name (str): Name of the project
        Returns:
            Dict[str, Any]: Project metadata
        """
        project_dir = os.path.join(self.projects_dir, project_name)
        if not os.path.exists(project_dir):
            raise ProjectError(f"Project '{project_name}' does not exist")
        metadata_path = os.path.join(project_dir, "project.json")
        if not os.path.exists(metadata_path):
            raise ProjectError(f"Project metadata file not found for '{project_name}'")
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            # Update last modified time
            metadata["last_modified"] = datetime.now().isoformat()
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            return metadata
        except Exception as e:
            raise ProjectError(f"Failed to load project metadata: {e}")
    def list_projects(self) -> List[Dict[str, Any]]:
        """
        List all available projects.
        Returns:
            List[Dict[str, Any]]: List of project information
        """
        projects = []
        if not os.path.exists(self.projects_dir):
            return projects
        for item in os.listdir(self.projects_dir):
            item_path = os.path.join(self.projects_dir, item)
            if os.path.isdir(item_path):
                try:
                    metadata_path = os.path.join(item_path, "project.json")
                    if os.path.exists(metadata_path):
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                        projects.append({
                            "id": item,  # Use folder name as ID
                            "name": metadata.get("project_name", item),
                            "author": metadata.get("author", ""),
                            "description": metadata.get("description", ""),
                            "created_at": metadata.get("created_at", ""),
                            "processing_status": metadata.get("processing_status", "created"),
                            "path": item_path
                        })
                except Exception as e:
                    logger.warning(f"Could not load project info for {item}: {e}")
        return projects
    def add_manuscript(self, project_name: str, manuscript_path: str, 
                      manuscript_name: Optional[str] = None) -> bool:
        """
        Add a manuscript file to a project.
        Args:
            project_name (str): Name of the project
            manuscript_path (str): Path to the manuscript file
            manuscript_name (str, optional): Name to give the manuscript in the project
        Returns:
            bool: True if manuscript was added successfully
        """
        # Validate manuscript file exists
        if not os.path.exists(manuscript_path):
            raise ProjectError(f"Manuscript file does not exist: {manuscript_path}")
        # Load project
        project_metadata = self.load_project(project_name)
        project_dir = os.path.join(self.projects_dir, project_name)
        # Determine manuscript name
        if not manuscript_name:
            manuscript_name = os.path.basename(manuscript_path)
        # Copy manuscript to project's manuscripts directory
        manuscripts_dir = os.path.join(project_dir, "manuscripts")
        destination_path = os.path.join(manuscripts_dir, manuscript_name)
        # Check if manuscript with this name already exists
        if os.path.exists(destination_path):
            raise ProjectError(f"Manuscript '{manuscript_name}' already exists in project")
        try:
            # Copy file
            shutil.copy2(manuscript_path, destination_path)
            # Update project metadata
            manuscript_info = {
                "name": manuscript_name,
                "original_path": manuscript_path,
                "project_path": destination_path,
                "added_at": datetime.now().isoformat(),
                "file_size": os.path.getsize(destination_path)
            }
            project_metadata["manuscripts"].append(manuscript_info)
            project_metadata["last_modified"] = datetime.now().isoformat()
            # Save updated metadata
            metadata_path = os.path.join(project_dir, "project.json")
            with open(metadata_path, 'w') as f:
                json.dump(project_metadata, f, indent=2)
            logger.info(f"Manuscript '{manuscript_name}' added to project '{project_name}'")
            return True
        except Exception as e:
            raise ProjectError(f"Failed to add manuscript: {e}")
    def get_project_manuscripts(self, project_name: str) -> List[Dict[str, Any]]:
        """
        Get list of manuscripts in a project.
        Args:
            project_name (str): Name of the project
        Returns:
            List[Dict[str, Any]]: List of manuscript information
        """
        project_metadata = self.load_project(project_name)
        return project_metadata.get("manuscripts", [])
    def remove_manuscript(self, project_name: str, manuscript_name: str) -> bool:
        """
        Remove a manuscript from a project.
        Args:
            project_name (str): Name of the project
            manuscript_name (str): Name of the manuscript to remove
        Returns:
            bool: True if manuscript was removed successfully
        """
        # Load project
        project_metadata = self.load_project(project_name)
        project_dir = os.path.join(self.projects_dir, project_name)
        # Find manuscript
        manuscript_info = None
        manuscript_index = None
        for i, ms in enumerate(project_metadata["manuscripts"]):
            if ms["name"] == manuscript_name:
                manuscript_info = ms
                manuscript_index = i
                break
        if not manuscript_info:
            raise ProjectError(f"Manuscript '{manuscript_name}' not found in project")
        try:
            # Remove manuscript file
            manuscript_path = manuscript_info["project_path"]
            if os.path.exists(manuscript_path):
                os.remove(manuscript_path)
            # Update project metadata
            project_metadata["manuscripts"].pop(manuscript_index)
            project_metadata["last_modified"] = datetime.now().isoformat()
            # Save updated metadata
            metadata_path = os.path.join(project_dir, "project.json")
            with open(metadata_path, 'w') as f:
                json.dump(project_metadata, f, indent=2)
            logger.info(f"Manuscript '{manuscript_name}' removed from project '{project_name}'")
            return True
        except Exception as e:
            raise ProjectError(f"Failed to remove manuscript: {e}")
    def update_project_status(self, project_name: str, status: str) -> bool:
        """
        Update the processing status of a project.
        Args:
            project_name (str): Name of the project
            status (str): New status
        Returns:
            bool: True if status was updated successfully
        """
        project_metadata = self.load_project(project_name)
        project_dir = os.path.join(self.projects_dir, project_name)
        try:
            project_metadata["processing_status"] = status
            project_metadata["last_modified"] = datetime.now().isoformat()
            metadata_path = os.path.join(project_dir, "project.json")
            with open(metadata_path, 'w') as f:
                json.dump(project_metadata, f, indent=2)
            logger.info(f"Project '{project_name}' status updated to '{status}'")
            return True
        except Exception as e:
            raise ProjectError(f"Failed to update project status: {e}")
    def backup_project(self, project_name: str, backup_name: Optional[str] = None) -> str:
        """
        Create a backup of a project.
        Args:
            project_name (str): Name of the project
            backup_name (str, optional): Name for the backup
        Returns:
            str: Path to the backup
        """
        project_dir = os.path.join(self.projects_dir, project_name)
        if not os.path.exists(project_dir):
            raise ProjectError(f"Project '{project_name}' does not exist")
        if not backup_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{project_name}_backup_{timestamp}"
        backups_dir = os.path.join(project_dir, "backups")
        backup_path = os.path.join(backups_dir, f"{backup_name}.zip")
        try:
            # Create zip archive of project
            shutil.make_archive(
                os.path.join(backups_dir, backup_name),
                'zip',
                project_dir
            )
            logger.info(f"Backup created: {backup_path}")
            return backup_path
        except Exception as e:
            raise ProjectError(f"Failed to create backup: {e}")
    def get_project_path(self, project_name: str) -> str:
        """
        Get the full path to a project directory.
        Args:
            project_name (str): Name of the project
        Returns:
            str: Full path to the project directory
        """
        project_dir = os.path.join(self.projects_dir, project_name)
        if not os.path.exists(project_dir):
            raise ProjectError(f"Project '{project_name}' does not exist")
        return project_dir