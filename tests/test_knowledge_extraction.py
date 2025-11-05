"""
Test the knowledge extraction system
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.george.llm_integration import create_george_ai
from backend.knowledge_extraction import KnowledgeExtractor

def test_knowledge_extraction():
    """Test knowledge extraction on a sample file."""
    
    # Initialize AI
    print("Initializing AI...")
    george_ai = create_george_ai(model="phi3:instruct")
    
    # Read test file
    test_file = Path("src/data/uploads/Chapter_1_-_A_Twist_Too_Far.md")
    if not test_file.exists():
        print(f"Test file not found: {test_file}")
        return
    
    with open(test_file, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Create knowledge extractor
    project_path = Path("src/data/projects/test_project")
    extractor = KnowledgeExtractor(george_ai, str(project_path))
    
    # Process manuscript (THIS IS THE SLOW PART - only done once)
    print("\n" + "="*60)
    print("PROCESSING MANUSCRIPT (this will take several minutes)")
    print("="*60 + "\n")
    
    summary = extractor.process_manuscript(text, test_file.name)
    
    print("\n" + "="*60)
    print("PROCESSING COMPLETE!")
    print("="*60)
    print(f"Total entities: {summary['total_entities']}")
    print(f"Characters: {summary['characters']}")
    print(f"Locations: {summary['locations']}")
    print(f"Terms: {summary['term']}")
    print(f"Knowledge base: {summary['kb_path']}")
    
    # Now test queries (THESE SHOULD BE FAST)
    print("\n" + "="*60)
    print("TESTING QUERIES (should be fast)")
    print("="*60 + "\n")
    
    queries = [
        "Who are the main characters?",
        "List all characters",
        "Tell me about Hugh",
        "Where does the story take place?",
        "What is the Twist Drive?"
    ]
    
    for query in queries:
        print(f"\nQ: {query}")
        result = extractor.answer_query(query)
        if result['success']:
            print(f"A: {result['response']}")
            print(f"   (Context size: {result['context_used']} chars)")
        else:
            print(f"ERROR: {result['error']}")
        print("-" * 60)

if __name__ == '__main__':
    test_knowledge_extraction()
