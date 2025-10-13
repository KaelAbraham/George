"""Example script demonstrating the text chunking and preprocessing pipeline."""
import sys
import os
import json
# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from parsers.document_parser import DocumentParser
from preprocessing.text_chunker import TextChunker
from preprocessing.text_preprocessor import TextPreprocessor
def main():
    """Demonstrate the text chunking and preprocessing pipeline."""
    # Initialize components
    parser = DocumentParser()
    chunker = TextChunker()
    preprocessor = TextPreprocessor()
    # Get the fixtures directory
    fixtures_dir = os.path.join(os.path.dirname(__file__), '..', 'tests', 'fixtures')
    # Test files
    test_files = [
        'sample.txt',
        'sample.md',
        'sample.docx'
    ]
    print("Text Chunking and Preprocessing Pipeline Demo")
    print("=" * 60)
    for filename in test_files:
        file_path = os.path.join(fixtures_dir, filename)
        if not os.path.exists(file_path):
            print(f"File not found: {filename}")
            continue
        print(f"\nProcessing: {filename}")
        print("-" * 40)
        try:
            # 1. Parse the document
            print("1. Parsing document...")
            parsed_result = parser.parse(file_path)
            content = parsed_result['content']
            print(f"   Extracted {len(content)} characters")
            # 2. Chunk the text
            print("2. Chunking text by paragraphs...")
            chunks = chunker.chunk_text(content, filename, chunk_strategy="paragraph")
            print(f"   Created {len(chunks)} chunks")
            # Display first chunk info
            if chunks:
                first_chunk = chunks[0]
                print(f"   First chunk ID: {first_chunk.chunk_id}")
                print(f"   First chunk content preview: {first_chunk.content[:50]}...")
                print(f"   First chunk position: {first_chunk.start_position}-{first_chunk.end_position}")
            # 3. Preprocess chunks
            print("3. Preprocessing chunks for NER...")
            chunk_dicts = [chunk.to_dict() for chunk in chunks]
            preprocessed_chunks = preprocessor.preprocess_chunks(chunk_dicts)
            print(f"   Preprocessed {len(preprocessed_chunks)} chunks")
            # Display first preprocessed chunk
            if preprocessed_chunks:
                first_processed = preprocessed_chunks[0]
                print(f"   First processed content preview: {first_processed['content'][:50]}...")
            # 4. Demonstrate other chunking strategies
            print("4. Alternative chunking strategies:")
            # Sentence chunking
            sent_chunks = chunker.chunk_text(content, filename, chunk_strategy="sentence")
            print(f"   Sentence chunking: {len(sent_chunks)} chunks")
            # Fixed-size chunking
            fixed_chunks = chunker.chunk_text(content, filename, chunk_strategy="fixed", chunk_size=100)
            print(f"   Fixed-size chunking (100 chars): {len(fixed_chunks)} chunks")
        except Exception as e:
            print(f"Error processing {filename}: {e}")
if __name__ == "__main__":
    main()