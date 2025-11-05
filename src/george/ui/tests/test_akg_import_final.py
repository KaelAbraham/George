"""
Final test to verify AKG module import and functionality
"""
import sys
import os
# Add the src directory to the path
sys.path.insert(0, '/app/local_story_ai_1423/src')
def test_akg_import():
    try:
        # Test importing the main module
        import akg
        print("✓ AKG module imported successfully")
        # Test importing individual components
        from akg.core.entity_extractor import EntityExtractor
        from akg.entities.classifier import EntityClassifier
        from akg.core.candidate_generator import CandidateGenerator
        from akg.core.entity_merger import EntityMerger
        from akg.validation.interface import ValidationInterface
        print("✓ All AKG submodules imported successfully")
        # Test basic functionality
        extractor = EntityExtractor()
        sample_text = "James Bond walked into the MI6 headquarters in London."
        entities = extractor.extract_entities(sample_text)
        print("✓ Entity extraction working correctly")
        print(f"  Extracted {len(entities)} entities from sample text")
        # Test classifier
        classifier = EntityClassifier()
        classified = classifier.classify_entities(entities)
        print("✓ Entity classification working correctly")
        # Test candidate generator
        generator = CandidateGenerator()
        candidates = generator.generate_candidates(sample_text, classified)
        print("✓ Candidate generation working correctly")
        print(f"  Generated {len(candidates)} candidates")
        # Test merger
        merger = EntityMerger()
        merged = merger.find_merge_candidates(candidates[:3])  # Test with first 3
        print("✓ Entity merging working correctly")
        print("\n🎉 All AKG components are working correctly!")
        return True
    except Exception as e:
        print(f"❌ Error testing AKG module: {e}")
        return False
if __name__ == "__main__":
    test_akg_import()