import os
from pathlib import Path
from george.parsers.parsers import read_manuscript_file
from george.knowledge_extraction.orchestrator import KnowledgeExtractor
from george.llm_integration import create_george_ai

def run_kb_generator_on_file(file_path):
    # Read the manuscript file
    content = read_manuscript_file(file_path)
    print(f"Loaded file: {file_path}\nWord count: {len(content.split())}")

    # Create the AI model (use the same as in the API)
    ai_kb_generator = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True)

    # Use a dummy project path (parent of file)
    project_path = str(Path(file_path).parent)
    extractor = KnowledgeExtractor(ai_kb_generator, project_path=project_path)

    # Use the filename only
    filename = os.path.basename(file_path)
    print(f"Running KB generator on: {filename}")
    result = extractor.generate_knowledge_base(filename)
    print("Result:")
    print(result)
    return result

if __name__ == "__main__":
    # Path to the EAWAN.txt file
    file_path = r"c:/Users/kael_/George/src/george/ui/src/data/uploads/EAWAN.txt"
    run_kb_generator_on_file(file_path)
