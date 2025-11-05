"""Core services for the filesystem server."""
import os
import codecs
import chardet
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

# Optional dependencies
try:
    import magic
    MAGIC_AVAILABLE = True
except (ImportError, OSError):
    MAGIC_AVAILABLE = False
    magic = None

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    DocxDocument = None

try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    markdown = None

logger = logging.getLogger(__name__)

class DocumentParserError(Exception):
    """Custom exception for document parsing errors."""
    pass

class DocumentParser:
    """A robust multi-format document parser for .docx, .md, and .txt files."""
    def __init__(self):
        self.supported_formats = {
            '.txt': 'Plain Text',
            '.md': 'Markdown',
            '.docx': 'Microsoft Word Document'
        }

    def detect_file_type(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise DocumentParserError(f"File not found: {file_path}")
        if MAGIC_AVAILABLE:
            try:
                mime = magic.from_file(file_path, mime=True)
                if mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                    return '.docx'
                elif mime == 'text/plain':
                    return '.txt'
            except Exception:
                pass
        _, ext = os.path.splitext(file_path.lower())
        return ext

    def detect_encoding(self, file_path: str) -> str:
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
                result = chardet.detect(raw_data)
                return result['encoding'] or 'utf-8'
        except Exception as e:
            raise DocumentParserError(f"Error detecting encoding: {str(e)}")

    def parse_docx(self, file_path: str) -> Dict[str, Any]:
        if not DOCX_AVAILABLE:
            raise DocumentParserError("python-docx library not available.")
        try:
            doc = DocxDocument(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            core_properties = doc.core_properties
            metadata = {
                'title': core_properties.title,
                'author': core_properties.author,
                'created': core_properties.created,
                'modified': core_properties.modified,
                'paragraph_count': len(doc.paragraphs)
            }
            return {'content': '\n'.join(paragraphs), 'metadata': metadata, 'format': 'docx'}
        except Exception as e:
            raise DocumentParserError(f"Error parsing .docx file: {str(e)}")

    def parse_markdown(self, file_path: str) -> Dict[str, Any]:
        if not MARKDOWN_AVAILABLE:
            raise DocumentParserError("markdown library not available.")
        try:
            encoding = self.detect_encoding(file_path)
            with codecs.open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            lines = content.split('\n')
            text_lines = []
            for line in lines:
                clean_line = line.lstrip('# ').replace('*', '').replace('_', '').replace('`', '')
                if clean_line.strip():
                    text_lines.append(clean_line)
            return {
                'content': '\n'.join(text_lines),
                'metadata': {'line_count': len(lines), 'encoding': encoding},
                'format': 'markdown'
            }
        except Exception as e:
            raise DocumentParserError(f"Error parsing .md file: {str(e)}")

    def parse_txt(self, file_path: str) -> Dict[str, Any]:
        try:
            encoding = self.detect_encoding(file_path)
            with codecs.open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            return {
                'content': content,
                'metadata': {'line_count': len(content.split('\n')), 'encoding': encoding},
                'format': 'txt'
            }
        except Exception as e:
            raise DocumentParserError(f"Error parsing .txt file: {str(e)}")

    def parse(self, file_path: str) -> Dict[str, Any]:
        file_type = self.detect_file_type(file_path)
        if file_type == '.docx':
            return self.parse_docx(file_path)
        elif file_type == '.md':
            return self.parse_markdown(file_path)
        elif file_type == '.txt':
            return self.parse_txt(file_path)
        else:
            try:
                return self.parse_txt(file_path)
            except DocumentParserError:
                raise DocumentParserError(f"Unsupported file format: {file_type}")

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
    """Splits text into chunks while preserving source attribution and metadata"""
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        logger.info(f"TextChunker initialized with chunk_size={chunk_size}, overlap={chunk_overlap}")

    def chunk_text(self, text: str, source_file: str, chapter: str = None) -> List[TextChunk]:
        try:
            paragraphs = self._split_into_paragraphs(text)
            chunks = self._create_chunks_from_paragraphs(paragraphs, source_file, chapter)
            logger.info(f"Created {len(chunks)} chunks from {source_file}")
            return chunks
        except Exception as e:
            logger.error(f"Failed to chunk text from {source_file}: {e}")
            raise

    def _split_into_paragraphs(self, text: str) -> List[Tuple[str, int, int]]:
        paragraphs = []
        pos = 0
        for paragraph_text in re.split(r'\n\s*\n', text):
            if not paragraph_text.strip():
                pos += len(paragraph_text) + 2
                continue
            start_pos = pos + len(paragraph_text) - len(paragraph_text.lstrip())
            end_pos = pos + len(paragraph_text)
            paragraphs.append((paragraph_text.strip(), start_pos, end_pos))
            pos += len(paragraph_text) + 2
        return paragraphs

    def _create_chunks_from_paragraphs(self, paragraphs: List[Tuple[str, int, int]], 
                                     source_file: str, chapter: str = None) -> List[TextChunk]:
        chunks = []
        current_chunk_text = ""
        current_chunk_start = None
        current_chunk_end = None
        paragraph_start = None
        paragraph_count = 0
        for i, (paragraph_text, para_start, para_end) in enumerate(paragraphs):
            if not current_chunk_text:
                current_chunk_start = para_start
                paragraph_start = i + 1
            
            if len(current_chunk_text) + len(paragraph_text) > self.chunk_size and current_chunk_text:
                chunks.append(TextChunk(
                    text=current_chunk_text.strip(),
                    source_file=source_file,
                    chapter=chapter,
                    paragraph_start=paragraph_start,
                    paragraph_end=i,
                    character_start=current_chunk_start,
                    character_end=current_chunk_end
                ))
                
                overlap_text = current_chunk_text[-self.chunk_overlap:]
                current_chunk_text = overlap_text
                current_chunk_start = (current_chunk_end - len(overlap_text)) if current_chunk_end else para_start
                paragraph_start = i

            current_chunk_text += ("\n\n" if current_chunk_text else "") + paragraph_text
            current_chunk_end = para_end
        
        if current_chunk_text:
            chunks.append(TextChunk(
                text=current_chunk_text.strip(),
                source_file=source_file,
                chapter=chapter,
                paragraph_start=paragraph_start,
                paragraph_end=len(paragraphs),
                character_start=current_chunk_start,
                character_end=current_chunk_end
            ))
        return chunks
