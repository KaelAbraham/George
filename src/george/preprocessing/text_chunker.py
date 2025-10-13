"""
Text Chunking System for the Knowledge Base
Preserves source attribution and creates searchable segments
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
logger = logging.getLogger(__name__)
@dataclass
class TextChunk:
    """Represents a chunk of text with metadata"""
    text: str
    source_file: str
    chapter: Optional[str] = None
    paragraph_start: Optional[int] = None
    paragraph_end: Optional[int] = None
    character_start: Optional[int] = None
    character_end: Optional[int] = None
    entities: List[str] = None
    def __post_init__(self):
        if self.entities is None:
            self.entities = []
class TextChunker:
    """
    Splits text into chunks while preserving source attribution and metadata
    """
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        """
        Initialize the text chunker
        Args:
            chunk_size (int): Target size of each chunk in characters
            chunk_overlap (int): Number of characters to overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        logger.info(f"TextChunker initialized with chunk_size={chunk_size}, overlap={chunk_overlap}")
    def chunk_text(self, text: str, source_file: str, chapter: str = None) -> List[TextChunk]:
        """
        Split text into chunks with metadata preservation
        Args:
            text (str): Text to chunk
            source_file (str): Source file identifier
            chapter (str, optional): Chapter/section name
        Returns:
            List[TextChunk]: List of text chunks with metadata
        """
        try:
            # Split text into paragraphs first
            paragraphs = self._split_into_paragraphs(text)
            # Create chunks from paragraphs
            chunks = self._create_chunks_from_paragraphs(
                paragraphs, source_file, chapter
            )
            logger.info(f"Created {len(chunks)} chunks from {source_file}")
            return chunks
        except Exception as e:
            logger.error(f"Failed to chunk text from {source_file}: {e}")
            raise
    def _split_into_paragraphs(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Split text into paragraphs while preserving character positions
        Args:
            text (str): Text to split
        Returns:
            List[Tuple[str, int, int]]: List of (paragraph_text, start_pos, end_pos)
        """
        paragraphs = []
        pos = 0
        # Split by double newlines (paragraph separators)
        for paragraph_text in re.split(r'\n\s*\n', text):
            # Skip empty paragraphs
            if not paragraph_text.strip():
                pos += len(paragraph_text) + 2  # +2 for the \n\n
                continue
            # Find the actual start position (skip leading whitespace)
            start_pos = pos + len(paragraph_text) - len(paragraph_text.lstrip())
            end_pos = pos + len(paragraph_text)
            paragraphs.append((paragraph_text.strip(), start_pos, end_pos))
            pos += len(paragraph_text) + 2  # +2 for the \n\n
        return paragraphs
    def _create_chunks_from_paragraphs(self, paragraphs: List[Tuple[str, int, int]], 
                                     source_file: str, chapter: str = None) -> List[TextChunk]:
        """
        Create chunks from paragraphs while maintaining overlap
        Args:
            paragraphs (List[Tuple[str, int, int]]): List of (text, start_pos, end_pos)
            source_file (str): Source file identifier
            chapter (str, optional): Chapter/section name
        Returns:
            List[TextChunk]: List of text chunks
        """
        chunks = []
        current_chunk_text = ""
        current_chunk_start = None
        current_chunk_end = None
        paragraph_start = None
        paragraph_count = 0
        for paragraph_text, para_start, para_end in paragraphs:
            # If this is the first paragraph of a potential chunk
            if not current_chunk_text:
                current_chunk_start = para_start
                paragraph_start = paragraph_count + 1
            # Check if adding this paragraph would exceed chunk size
            if len(current_chunk_text) + len(paragraph_text) > self.chunk_size and current_chunk_text:
                # Create chunk with current content
                chunk = TextChunk(
                    text=current_chunk_text.strip(),
                    source_file=source_file,
                    chapter=chapter,
                    paragraph_start=paragraph_start,
                    paragraph_end=paragraph_count,
                    character_start=current_chunk_start,
                    character_end=current_chunk_end
                )
                chunks.append(chunk)
                # Start new chunk with overlap
                # Calculate overlap by taking the last chunk_overlap characters
                overlap_text = current_chunk_text[-self.chunk_overlap:] if len(current_chunk_text) > self.chunk_overlap else current_chunk_text
                current_chunk_text = overlap_text
                current_chunk_start = current_chunk_end - len(overlap_text) if current_chunk_end else para_start
                paragraph_start = paragraph_count
            # Add paragraph to current chunk
            if current_chunk_text:
                current_chunk_text += "\n\n" + paragraph_text
            else:
                current_chunk_text = paragraph_text
            current_chunk_end = para_end
            paragraph_count += 1
        # Don't forget the last chunk
        if current_chunk_text:
            chunk = TextChunk(
                text=current_chunk_text.strip(),
                source_file=source_file,
                chapter=chapter,
                paragraph_start=paragraph_start,
                paragraph_end=paragraph_count,
                character_start=current_chunk_start,
                character_end=current_chunk_end
            )
            chunks.append(chunk)
        return chunks
    def chunk_with_entity_detection(self, text: str, source_file: str, 
                                  entities: List[Dict[str, Any]], chapter: str = None) -> List[TextChunk]:
        """
        Chunk text and associate entities with chunks based on text positions
        Args:
            text (str): Text to chunk
            source_file (str): Source file identifier
            entities (List[Dict]): List of entity dictionaries with position info
            chapter (str, optional): Chapter/section name
        Returns:
            List[TextChunk]: List of text chunks with associated entities
        """
        # First create basic chunks
        chunks = self.chunk_text(text, source_file, chapter)
        # Associate entities with chunks based on position
        for chunk in chunks:
            chunk_entities = []
            for entity in entities:
                # Check if entity position overlaps with chunk position
                if self._positions_overlap(
                    chunk.character_start, chunk.character_end,
                    entity.get('character_start'), entity.get('character_end')
                ):
                    chunk_entities.append(entity['name'])
            chunk.entities = chunk_entities
        return chunks
    def _positions_overlap(self, start1: int, end1: int, start2: int, end2: int) -> bool:
        """
        Check if two character position ranges overlap
        Args:
            start1 (int): Start of first range
            end1 (int): End of first range
            start2 (int): Start of second range
            end2 (int): End of second range
        Returns:
            bool: True if ranges overlap
        """
        return max(start1, start2) <= min(end1, end2)
def test_text_chunker():
    """Test the TextChunker functionality"""
    print("Testing TextChunker...")
    # Sample text
    sample_text = """This is the first paragraph of our sample document. It contains some 
    introductory information that we want to process and chunk.
    This is the second paragraph with more detailed content. We can see how 
    the chunking system handles paragraph boundaries and creates appropriate segments.
    This is the third paragraph which continues our example. The chunking system 
    should properly handle this text and create meaningful chunks.
    This is the fourth and final paragraph of our sample text. It demonstrates 
    how the system handles the end of a document."""
    # Initialize chunker
    chunker = TextChunker(chunk_size=200, chunk_overlap=30)
    # Test basic chunking
    chunks = chunker.chunk_text(sample_text, "test.txt", "Chapter 1")
    print(f"✓ Created {len(chunks)} chunks")
    # Check first chunk
    if chunks:
        print(f"✓ First chunk length: {len(chunks[0].text)} characters")
        print(f"✓ First chunk position: {chunks[0].character_start}-{chunks[0].character_end}")
    # Test with entities
    entities = [
        {"name": "Sample Document", "character_start": 30, "character_end": 45},
        {"name": "Detailed Content", "character_start": 180, "character_end": 195}
    ]
    chunks_with_entities = chunker.chunk_with_entity_detection(sample_text, "test.txt", entities, "Chapter 1")
    print(f"✓ Created {len(chunks_with_entities)} chunks with entity associations")
    # Check entity associations
    entities_found = 0
    for chunk in chunks_with_entities:
        if chunk.entities:
            entities_found += len(chunk.entities)
    print(f"✓ Associated {entities_found} entity references with chunks")
    print("TextChunker testing completed successfully!")
if __name__ == "__main__":
    test_text_chunker()