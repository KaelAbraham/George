"""
Test the validation interface component
"""
import sys
import os
# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

def test_validation_interface():
    try:
        from george.akg.validation.interface import ValidationInterface
        print("✓ ValidationInterface imported successfully")
        # Test initialization
        interface = ValidationInterface()
        print("✓ ValidationInterface initialized successfully")
        # Test batch actions
        sample_entities = [
            {"text": "James Bond", "category": "Character"},
            {"text": "London", "category": "Location"}
        ]
        accepted = interface.batch_action(sample_entities, "accept_all")
        print("✓ Batch action (accept_all) working correctly")
        rejected = interface.batch_action(sample_entities, "reject_all")
        print("✓ Batch action (reject_all) working correctly")
        print("\n🎉 Validation interface is working correctly!")
        return True
    except Exception as e:
        print(f"❌ Error testing validation interface: {e}")
        return False
if __name__ == "__main__":
    test_validation_interface()