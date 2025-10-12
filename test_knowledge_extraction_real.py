"""
Test knowledge extraction system directly
"""
import sys
from pathlib import Path

# Add src/george to path
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'george'))

print("🔍 Testing Knowledge Extraction System...")

# Test imports
try:
    from llm_integration import create_george_ai
    print("✅ llm_integration imported")
except Exception as e:
    print(f"❌ Failed to import llm_integration: {e}")
    sys.exit(1)

try:
    from knowledge_extraction.orchestrator import KnowledgeExtractor
    print("✅ KnowledgeExtractor imported")
except Exception as e:
    print(f"❌ Failed to import KnowledgeExtractor: {e}")
    sys.exit(1)

# Create AI instance
try:
    george_ai = create_george_ai(model="phi3:instruct")
    print("✅ George AI created")
except Exception as e:
    print(f"❌ Failed to create George AI: {e}")
    sys.exit(1)

# Test with sample content
test_content = """
Chapter 1: The Beginning

"Hello, Sarah," said John as he walked into the coffee shop. Sarah looked up from her book and smiled.

"Hi John! How are you doing?" she replied warmly.

John sat down at the table across from her. The coffee shop, called The Daily Grind, was their favorite meeting spot.

Later that evening, they walked through Central Park, discussing their plans for the weekend.
"""

# Create test project directory
test_project_path = Path(__file__).parent / 'data' / 'uploads' / 'projects' / 'test_extraction'
test_project_path.mkdir(parents=True, exist_ok=True)

print(f"📁 Test project path: {test_project_path}")

# Create extractor
try:
    extractor = KnowledgeExtractor(george_ai, str(test_project_path))
    print("✅ KnowledgeExtractor instance created")
except Exception as e:
    print(f"❌ Failed to create KnowledgeExtractor: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Process manuscript
print("\n🚀 Starting manuscript processing...")
try:
    summary = extractor.process_manuscript(test_content, "test.txt")
    print(f"\n✅ Processing complete!")
    print(f"📊 Summary: {summary}")
    
    # Check if files were created
    kb_path = test_project_path / 'knowledge_base'
    if kb_path.exists():
        files = list(kb_path.glob('*.md'))
        print(f"\n📄 Created {len(files)} profile files:")
        for f in files:
            print(f"  - {f.name}")
    else:
        print(f"⚠️  Knowledge base directory not created: {kb_path}")
        
except Exception as e:
    print(f"❌ Processing failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ All tests passed!")
