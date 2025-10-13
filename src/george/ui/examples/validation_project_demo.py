"""Example script demonstrating document validation and project management."""
import sys
import os
import tempfile
import json
# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from validation.document_validator import DocumentValidator
from utils.project_manager import ProjectManager
def demonstrate_document_validation():
    """Demonstrate document validation functionality."""
    print("DOCUMENT VALIDATION DEMO")
    print("=" * 40)
    validator = DocumentValidator()
    fixtures_dir = os.path.join(os.path.dirname(__file__), '..', 'tests', 'fixtures')
    # Test files
    test_files = [
        'sample.txt',
        'sample.md',
        'sample.docx'
    ]
    for filename in test_files:
        file_path = os.path.join(fixtures_dir, filename)
        if not os.path.exists(file_path):
            print(f"File not found: {filename}")
            continue
        print(f"\nValidating: {filename}")
        print("-" * 30)
        try:
            result = validator.validate(file_path)
            print(f"Status: {result['status']}")
            if result['errors']:
                print("Errors:")
                for error in result['errors']:
                    print(f"  - {error}")
            else:
                print("No errors found")
            if result['warnings']:
                print("Warnings:")
                for warning in result['warnings']:
                    print(f"  - {warning}")
            print("Details:")
            for key, value in result['details'].items():
                print(f"  {key}: {value}")
        except Exception as e:
            print(f"Unexpected error: {e}")
def demonstrate_project_management():
    """Demonstrate project management functionality."""
    print("\n\nPROJECT MANAGEMENT DEMO")
    print("=" * 40)
    # Create a temporary directory for projects
    with tempfile.TemporaryDirectory() as temp_dir:
        project_manager = ProjectManager(temp_dir)
        try:
            # 1. Create a project
            print("1. Creating project...")
            project_name = "demo_project"
            project_dir = project_manager.create_project(
                project_name, 
                "Demo Author", 
                "A demonstration project for validation and project management"
            )
            print(f"   Project created at: {project_dir}")
            # 2. List projects
            print("\n2. Listing projects...")
            projects = project_manager.list_projects()
            for project in projects:
                print(f"   - {project['name']} by {project['author']}")
            # 3. Load project
            print("\n3. Loading project...")
            metadata = project_manager.load_project(project_name)
            print(f"   Project name: {metadata['project_name']}")
            print(f"   Author: {metadata['author']}")
            print(f"   Created: {metadata['created_at']}")
            print(f"   Status: {metadata['processing_status']}")
            # 4. Add manuscripts
            print("\n4. Adding manuscripts...")
            fixtures_dir = os.path.join(os.path.dirname(__file__), '..', 'tests', 'fixtures')
            for filename in ['sample.txt', 'sample.md']:
                file_path = os.path.join(fixtures_dir, filename)
                if os.path.exists(file_path):
                    result = project_manager.add_manuscript(project_name, file_path, filename)
                    print(f"   Added {filename}: {result}")
            # 5. List manuscripts
            print("\n5. Listing manuscripts...")
            manuscripts = project_manager.get_project_manuscripts(project_name)
            for manuscript in manuscripts:
                print(f"   - {manuscript['name']} ({manuscript['file_size']} bytes)")
            # 6. Update project status
            print("\n6. Updating project status...")
            result = project_manager.update_project_status(project_name, "processing")
            print(f"   Status updated: {result}")
            # 7. Verify status update
            metadata = project_manager.load_project(project_name)
            print(f"   Current status: {metadata['processing_status']}")
            print("\n✓ Project management demonstration completed successfully!")
        except Exception as e:
            print(f"Error in project management demo: {e}")
            import traceback
            traceback.print_exc()
def main():
    """Main demonstration function."""
    print("VALIDATION AND PROJECT MANAGEMENT PIPELINE DEMO")
    print("=" * 60)
    demonstrate_document_validation()
    demonstrate_project_management()
    print("\n" + "=" * 60)
    print("✓ All demonstrations completed successfully!")
if __name__ == "__main__":
    main()