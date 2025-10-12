"""Text preprocessing pipeline for NER analysis preparation."""
import re
import unicodedata
from typing import List, Dict, Any
class TextPreprocessor:
    """Text preprocessing pipeline to prepare text for NER analysis."""
    def __init__(self):
        """Initialize the text preprocessor."""
        pass
    def normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace in text.
        Args:
            text (str): Input text
        Returns:
            str: Text with normalized whitespace
        """
        # Replace multiple whitespace characters with single space
        text = re.sub(r'\s+', ' ', text)
        # Strip leading/trailing whitespace
        return text.strip()
    def normalize_unicode(self, text: str) -> str:
        """
        Normalize Unicode characters to ensure consistency.
        Args:
            text (str): Input text
        Returns:
            str: Text with normalized Unicode
        """
        # Normalize to NFD (Canonical Decomposition)
        text = unicodedata.normalize('NFD', text)
        # Convert back to NFC (Canonical Decomposition followed by Canonical Composition)
        return unicodedata.normalize('NFC', text)
    def clean_text(self, text: str) -> str:
        """
        Clean text by removing formatting artifacts while preserving meaning.
        Args:
            text (str): Input text
        Returns:
            str: Cleaned text
        """
        # Remove extra whitespace
        text = self.normalize_whitespace(text)
        # Remove zero-width characters
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
        # Normalize quotes
        text = re.sub(r'[""''`]', '"', text)
        # Normalize dashes
        text = re.sub(r'[-\u2013\u2014]', '-', text)
        return text
    def prepare_for_ner(self, text: str) -> str:
        """
        Prepare text specifically for NER analysis.
        Args:
            text (str): Input text
        Returns:
            str: Text prepared for NER
        """
        # Normalize Unicode characters
        text = self.normalize_unicode(text)
        # Clean text
        text = self.clean_text(text)
        # Ensure proper sentence boundaries (for better NER)
        # Add space after punctuation if missing
        text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
        return text
    def preprocess_chunk(self, chunk_content: str) -> str:
        """
        Preprocess a text chunk for NER analysis.
        Args:
            chunk_content (str): Content of a text chunk
        Returns:
            str: Preprocessed text
        """
        return self.prepare_for_ner(chunk_content)
    def preprocess_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Preprocess a list of text chunks.
        Args:
            chunks (List[Dict[str, Any]]): List of chunk dictionaries
        Returns:
            List[Dict[str, Any]]: List of preprocessed chunks
        """
        preprocessed_chunks = []
        for chunk in chunks:
            # Make a copy to avoid modifying the original
            processed_chunk = chunk.copy()
            processed_chunk['content'] = self.preprocess_chunk(chunk['content'])
            preprocessed_chunks.append(processed_chunk)
        return preprocessed_chunks