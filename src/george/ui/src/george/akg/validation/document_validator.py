"""Document validation utilities for file integrity, encoding, and structure checks."""
import os
import mimetypes
import chardet
import magic
from typing import Dict, Any, Tuple, List
import logging
# Set up logger
logger = logging.getLogger(__name__)
class DocumentValidationError(Exception):
    """Custom exception for document validation errors."""
    pass
class DocumentValidator:
    """Document validation utilities for ensuring file quality and integrity."""
    def __init__(self):
        """Initialize the document validator."""
        # Supported file extensions
        self.supported_extensions = {'.txt', '.md', '.docx'}
        # Minimum and maximum file sizes (in bytes)
        self.min_file_size = 10  # 10 bytes minimum
        self.max_file_size = 50 * 1024 * 1024  # 50 MB maximum
        # Valid text encodings
        self.valid_encodings = {'utf-8', 'utf-16', 'ascii', 'iso-8859-1'}
    def validate_file_exists(self, file_path: str) -> bool:
        """
        Check if a file exists and is accessible.
        Args:
            file_path (str): Path to the file
        Returns:
            bool: True if file exists and is accessible
        """
        if not os.path.exists(file_path):
            raise DocumentValidationError(f"File does not exist: {file_path}")
        if not os.path.isfile(file_path):
            raise DocumentValidationError(f"Path is not a file: {file_path}")
        if not os.access(file_path, os.R_OK):
            raise DocumentValidationError(f"File is not readable: {file_path}")
        return True
    def validate_file_size(self, file_path: str) -> bool:
        """
        Check if file size is within acceptable limits.
        Args:
            file_path (str): Path to the file
        Returns:
            bool: True if file size is acceptable
        """
        try:
            size = os.path.getsize(file_path)
        except OSError as e:
            raise DocumentValidationError(f"Error getting file size: {e}")
        if size < self.min_file_size:
            raise DocumentValidationError(
                f"File is too small ({size} bytes). Minimum size is {self.min_file_size} bytes."
            )
        if size > self.max_file_size:
            raise DocumentValidationError(
                f"File is too large ({size} bytes). Maximum size is {self.max_file_size} bytes."
            )
        return True
    def validate_file_extension(self, file_path: str) -> bool:
        """
        Check if file extension is supported.
        Args:
            file_path (str): Path to the file
        Returns:
            bool: True if file extension is supported
        """
        _, ext = os.path.splitext(file_path.lower())
        if ext not in self.supported_extensions:
            raise DocumentValidationError(
                f"Unsupported file extension: {ext}. Supported extensions: {self.supported_extensions}"
            )
        return True
    def detect_file_type(self, file_path: str) -> str:
        """
        Detect file type using multiple methods.
        Args:
            file_path (str): Path to the file
        Returns:
            str: Detected MIME type
        """
        # Method 1: Using python-magic
        try:
            mime_type = magic.from_file(file_path, mime=True)
            if mime_type:
                return mime_type
        except Exception as e:
            logger.warning(f"Magic detection failed: {e}")
        # Method 2: Using mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            return mime_type
        # Method 3: File extension
        _, ext = os.path.splitext(file_path.lower())
        extension_map = {
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        return extension_map.get(ext, 'application/octet-stream')
    def validate_file_type(self, file_path: str) -> bool:
        """
        Validate that file type is appropriate for processing.
        Args:
            file_path (str): Path to the file
        Returns:
            bool: True if file type is valid
        """
        mime_type = self.detect_file_type(file_path)
        valid_mime_types = {
            'text/plain',
            'text/markdown',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        if mime_type not in valid_mime_types:
            # Check if it's a text-based file that might be processable
            if mime_type.startswith('text/'):
                logger.warning(f"Unexpected text MIME type: {mime_type}")
            else:
                raise DocumentValidationError(
                    f"Invalid file type: {mime_type}. Expected text-based document."
                )
        return True
    def detect_encoding(self, file_path: str) -> str:
        """
        Detect text encoding of a file.
        Args:
            file_path (str): Path to the file
        Returns:
            str: Detected encoding
        """
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)  # Read first 10KB for efficiency
                result = chardet.detect(raw_data)
                return result['encoding']
        except Exception as e:
            raise DocumentValidationError(f"Error detecting encoding: {e}")
    def validate_encoding(self, file_path: str) -> bool:
        """
        Validate that file encoding is supported.
        Args:
            file_path (str): Path to the file
        Returns:
            bool: True if encoding is supported
        """
        encoding = self.detect_encoding(file_path)
        if not encoding:
            raise DocumentValidationError("Could not detect file encoding")
        # Check if encoding is in our valid encodings or is a variant
        encoding_lower = encoding.lower()
        valid_encodings_lower = {e.lower() for e in self.valid_encodings}
        if encoding_lower not in valid_encodings_lower:
            # Check for common encoding variants
            if not any(valid in encoding_lower for valid in valid_encodings_lower):
                logger.warning(f"Unusual encoding detected: {encoding}. Attempting to proceed.")
        return True
    def validate_text_content(self, file_path: str) -> bool:
        """
        Validate that file contains text content (not binary).
        Args:
            file_path (str): Path to the file
        Returns:
            bool: True if file contains text content
        """
        try:
            encoding = self.detect_encoding(file_path)
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                # Read a sample of the content
                sample = f.read(1000)
                # Check if sample contains mostly text characters
                if len(sample) == 0:
                    raise DocumentValidationError("File appears to be empty")
                # Calculate text ratio (printable characters vs total)
                text_chars = sum(1 for c in sample if c.isprintable() or c.isspace())
                text_ratio = text_chars / len(sample) if sample else 0
                if text_ratio < 0.7:  # Less than 70% text characters
                    raise DocumentValidationError(
                        f"File appears to contain binary data (text ratio: {text_ratio:.2f})"
                    )
            return True
        except DocumentValidationError:
            raise
        except Exception as e:
            raise DocumentValidationError(f"Error validating text content: {e}")
    def validate_document_structure(self, file_path: str) -> bool:
        """
        Validate document structure based on file type.
        Args:
            file_path (str): Path to the file
        Returns:
            bool: True if document structure is valid
        """
        _, ext = os.path.splitext(file_path.lower())
        if ext == '.docx':
            # For DOCX files, try to parse with python-docx
            try:
                from docx import Document
                doc = Document(file_path)
                # Try to access basic properties to ensure it's a valid DOCX
                _ = doc.paragraphs
                return True
            except Exception as e:
                raise DocumentValidationError(f"Invalid DOCX structure: {e}")
        elif ext in ['.txt', '.md']:
            # For text files, basic validation is sufficient
            return True
        return True
    def validate(self, file_path: str) -> Dict[str, Any]:
        """
        Run all validations on a document file.
        Args:
            file_path (str): Path to the file
        Returns:
            Dict[str, Any]: Validation results with status and details
        """
        validation_results = {
            'file_path': file_path,
            'status': 'valid',
            'errors': [],
            'warnings': [],
            'details': {}
        }
        try:
            # Run all validations
            self.validate_file_exists(file_path)
            validation_results['details']['file_exists'] = True
            self.validate_file_size(file_path)
            validation_results['details']['file_size_valid'] = True
            self.validate_file_extension(file_path)
            validation_results['details']['extension_valid'] = True
            mime_type = self.detect_file_type(file_path)
            validation_results['details']['mime_type'] = mime_type
            self.validate_file_type(file_path)
            validation_results['details']['file_type_valid'] = True
            encoding = self.detect_encoding(file_path)
            validation_results['details']['encoding'] = encoding
            self.validate_encoding(file_path)
            validation_results['details']['encoding_valid'] = True
            self.validate_text_content(file_path)
            validation_results['details']['text_content_valid'] = True
            self.validate_document_structure(file_path)
            validation_results['details']['structure_valid'] = True
        except DocumentValidationError as e:
            validation_results['status'] = 'invalid'
            validation_results['errors'].append(str(e))
        except Exception as e:
            validation_results['status'] = 'error'
            validation_results['errors'].append(f"Unexpected error: {e}")
        return validation_results
    def batch_validate(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Validate multiple files.
        Args:
            file_paths (List[str]): List of file paths to validate
        Returns:
            List[Dict[str, Any]]: List of validation results
        """
        results = []
        for file_path in file_paths:
            result = self.validate(file_path)
            results.append(result)
        return results