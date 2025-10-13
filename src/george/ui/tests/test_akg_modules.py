import sys
import os
# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

def test_akg_modules():
    try:
        # Test individual components
        from george.akg.core.entity_extractor import EntityExtractor
        extractor = EntityExtractor()
        print("EntityExtractor imported and initialized successfully")
        
        from george.akg.validation.interface import ValidationInterface
        interface = ValidationInterface()
        print("ValidationInterface imported and initialized successfully")
        
        # Note: Other AKG components like EntityClassifier, CandidateGenerator, and EntityMerger
        # may need to be implemented or their imports updated
        
        print("Available AKG modules imported successfully!")
        return True
    except ImportError as e:
        print(f"Failed to import AKG modules: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    test_akg_modules()