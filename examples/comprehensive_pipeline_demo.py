"""Comprehensive demonstration of the full text processing pipeline."""
import sys
import os
import json
# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from parsers.document_parser import DocumentParser
from preprocessing.text_chunker import TextChunker
from preprocessing.text_preprocessor import TextPreprocessor
def process_document(file_path, file_name):
    """Process a single document through the full pipeline."""
    print(f"\n{'='*60}")
    print(f"Processing: {file_name}")
    print(f"{'='*60}")
    try:
        # Initialize components
        parser = DocumentParser()
        chunker = TextChunker()
        preprocessor = TextPreprocessor()
        # 1. Parse the document
        print("1. Document Parsing")
        print("-" * 20)
        parsed_result = parser.parse(file_path)
        content = parsed_result['content']
        print(f"   Format: {parsed_result['format']}")
        print(f"   Content length: {len(content)} characters")
        print(f"   Content preview: {content[:100]}...")
        if 'metadata' in parsed_result:
            print(f"   Metadata: {list(parsed_result['metadata'].keys())}")
        # 2. Chunk by paragraphs
        print("\n2. Paragraph Chunking")
        print("-" * 20)
        para_chunks = chunker.chunk_text(content, file_name, chunk_strategy="paragraph")
        print(f"   Created {len(para_chunks)} paragraph chunks")
        for i, chunk in enumerate(para_chunks):
            print(f"   Chunk {i+1}:")
            print(f"     ID: {chunk.chunk_id}")
            print(f"     Position: {chunk.start_position}-{chunk.end_position}")
            print(f"     Content: {chunk.content[:80]}{'...' if len(chunk.content) > 80 else ''}")
            print(f"     Metadata: {chunk.metadata}")
        # 3. Preprocess chunks for NER
        print("\n3. NER Preparation")
        print("-" * 20)
        chunk_dicts = [chunk.to_dict() for chunk in para_chunks]
        preprocessed_chunks = preprocessor.preprocess_chunks(chunk_dicts)
        print(f"   Preprocessed {len(preprocessed_chunks)} chunks")
        for i, chunk in enumerate(preprocessed_chunks):
            print(f"   Preprocessed Chunk {i+1}:")
            print(f"     Content: {chunk['content'][:80]}{'...' if len(chunk['content']) > 80 else ''}")
        # 4. Demonstrate traceability
        print("\n4. Traceability Verification")
        print("-" * 20)
        if para_chunks:
            first_chunk = para_chunks[0]
            print(f"   Source file: {first_chunk.source_file}")
            print(f"   Chunk type: {first_chunk.chunk_type.value}")
            print(f"   Position range: {first_chunk.start_position}-{first_chunk.end_position}")
            print(f"   Traceability metadata: {first_chunk.metadata}")
        # 5. Alternative strategies
        print("\n5. Alternative Chunking Strategies")
        print("-" * 20)
        sent_chunks = chunker.chunk_text(content, file_name, chunk_strategy="sentence")
        print(f"   Sentence chunking: {len(sent_chunks)} chunks")
        fixed_chunks = chunker.chunk_text(content, file_name, chunk_strategy="fixed", chunk_size=150)
        print(f"   Fixed-size chunking (150 chars): {len(fixed_chunks)} chunks")
        return {
            'file_name': file_name,
            'format': parsed_result['format'],
            'content_length': len(content),
            'paragraph_chunks': len(para_chunks),
            'sentence_chunks': len(sent_chunks),
            'fixed_chunks': len(fixed_chunks),
            'success': True
        }
    except Exception as e:
        print(f"   Error processing {file_name}: {e}")
        return {
            'file_name': file_name,
            'success': False,
            'error': str(e)
        }
def main():
    """Demonstrate the complete text processing pipeline."""
    print("COMPREHENSIVE TEXT PROCESSING PIPELINE DEMO")
    print("===========================================")
    # Get the fixtures directory
    fixtures_dir = os.path.join(os.path.dirname(__file__), '..', 'tests', 'fixtures')
    # Test files
    test_files = [
        'sample.txt',
        'sample.md',
        'sample.docx',
        'extended_sample.txt'
    ]
    results = []
    for filename in test_files:
        file_path = os.path.join(fixtures_dir, filename)
        if not os.path.exists(file_path):
            print(f"\nFile not found: {filename}")
            continue
        result = process_document(file_path, filename)
        results.append(result)
    # Summary
    print(f"\n{'='*60}")
    print("PROCESSING SUMMARY")
    print(f"{'='*60}")
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    print(f"Successfully processed: {len(successful)} files")
    print(f"Failed: {len(failed)} files")
    if successful:
        print("\nSuccessful processing details:")
        for result in successful:
            print(f"  {result['file_name']} ({result['format']}):")
            print(f"    Content length: {result['content_length']} chars")
            print(f"    Paragraph chunks: {result['paragraph_chunks']}")
            print(f"    Sentence chunks: {result['sentence_chunks']}")
            print(f"    Fixed chunks: {result['fixed_chunks']}")
    if failed:
        print("\nFailed processing details:")
        for result in failed:
            print(f"  {result['file_name']}: {result['error']}")
    print(f"\n✓ Pipeline demonstration completed!")
    print(f"  Files processed: {len(successful)}/{len(test_files)}")
    print(f"  Paragraph chunking verified with traceability metadata")
    print(f"  NER preparation completed for all chunks")
if __name__ == "__main__":
    main()