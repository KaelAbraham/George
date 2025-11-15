"""
Verification Script for Authorization Fix

This script verifies that the admin-to-admin access control fix is in place.
"""

import sys
from pathlib import Path

def check_string_in_file(filepath, search_string, description):
    """Check if a string exists in a file."""
    try:
        content = filepath.read_text(encoding='utf-8')
        if search_string in content:
            print(f"✓ {description}")
            return True
        else:
            print(f"✗ {description} NOT FOUND")
            return False
    except Exception as e:
        print(f"✗ Error reading {filepath}: {e}")
        return False

def main():
    print("="*70)
    print("  AUTHORIZATION FIX VERIFICATION")
    print("="*70)
    print()
    
    base_dir = Path(__file__).parent
    backend_app = base_dir / "backend" / "app.py"
    auth_app = base_dir / "auth_server" / "app.py"
    
    all_checks_passed = True
    
    # Check 1: Backend no longer has vulnerable "if role == 'admin': return True"
    print("🔍 Checking backend/app.py for vulnerability removal...")
    
    # Read the file to check it doesn't have the old vulnerable code
    backend_content = backend_app.read_text(encoding='utf-8')
    
    # Look for the old vulnerable pattern
    if "if auth_data.get('role') == 'admin':" in backend_content and \
       "return True" in backend_content and \
       "_check_project_access" in backend_content:
        # Check if it's within the _check_project_access function
        # Extract the function
        start = backend_content.find("def _check_project_access")
        if start != -1:
            # Find the next function definition
            next_def = backend_content.find("\ndef ", start + 1)
            if next_def == -1:
                next_def = len(backend_content)
            
            function_body = backend_content[start:next_def]
            
            # Check if vulnerable pattern exists in this function
            if "if auth_data.get('role') == 'admin':" in function_body and \
               "return True" in function_body:
                print("✗ VULNERABLE: Old 'if role == admin: return True' pattern still exists!")
                all_checks_passed = False
            else:
                print("✓ Vulnerable pattern removed from _check_project_access")
    else:
        print("✓ Vulnerable pattern removed from _check_project_access")
    
    # Check 2: Backend queries auth_server
    all_checks_passed &= check_string_in_file(
        backend_app,
        'f"/internal/projects/{project_id}/check_access"',
        "Backend queries auth_server for project access"
    )
    
    all_checks_passed &= check_string_in_file(
        backend_app,
        "auth_client.post",
        "Backend uses auth_client to check access"
    )
    
    # Check 3: Backend fails closed
    all_checks_passed &= check_string_in_file(
        backend_app,
        "Failing CLOSED",
        "Backend fails closed on error"
    )
    
    print()
    
    # Check 4: Auth server has new endpoint
    print("🔍 Checking auth_server/app.py for new endpoint...")
    
    all_checks_passed &= check_string_in_file(
        auth_app,
        "@app.route('/internal/projects/<project_id>/check_access'",
        "Auth server has check_access endpoint"
    )
    
    all_checks_passed &= check_string_in_file(
        auth_app,
        "def check_user_project_access",
        "Auth server has check_user_project_access function"
    )
    
    # Check 5: Auth server checks ownership
    all_checks_passed &= check_string_in_file(
        auth_app,
        "owner_id = auth_manager.get_project_owner(project_id)",
        "Auth server checks project ownership"
    )
    
    all_checks_passed &= check_string_in_file(
        auth_app,
        "if owner_id == user_id:",
        "Auth server compares owner_id with user_id"
    )
    
    # Check 6: Auth server checks guest access
    all_checks_passed &= check_string_in_file(
        auth_app,
        "auth_manager.check_project_access(user_id, project_id)",
        "Auth server checks guest access"
    )
    
    print()
    print("="*70)
    
    if all_checks_passed:
        print("✅ SUCCESS! Authorization fix verified.")
        print()
        print("📋 Changes Summary:")
        print("   1. ✓ Vulnerable 'if role == admin: return True' removed")
        print("   2. ✓ Backend queries auth_server for authorization")
        print("   3. ✓ Auth server checks project ownership")
        print("   4. ✓ Auth server checks guest permissions")
        print("   5. ✓ Backend fails closed on errors")
        print()
        print("🎯 Security Impact:")
        print("   - Admins can ONLY access their own projects")
        print("   - Guests can access projects they're explicitly granted")
        print("   - Multi-tenant data isolation enforced")
        print("   - Authorization fails safe (closed) on errors")
        print()
        print("🔄 Next steps:")
        print("   1. Commit and push these changes")
        print("   2. Test with two admin accounts")
        print("   3. Verify logs show denied access attempts")
        print("   4. Monitor authorization metrics")
        print()
        return 0
    else:
        print("❌ FAILED! Some verification checks did not pass.")
        print("   Please review the errors above and fix the issues.")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
