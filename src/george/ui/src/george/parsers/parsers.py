import os
import docx
import markdown
from chardet.universaldetector import UniversalDetector

def read_manuscript_file(file_path: str) -> str:
    """
    Reads the content of a manuscript file, supporting .txt, .md, and .docx.

    Args:
        file_path (str): The full path to the manuscript file.

    Returns:
        str: The text content of the file.
        
    Raises:
        ValueError: If the file type is unsupported.
    """
    _, extension = os.path.splitext(file_path)
    extension = extension.lower()

    if extension == '.txt' or extension == '.md':
        # Detect encoding to handle various text files gracefully
        detector = UniversalDetector()
        with open(file_path, 'rb') as f:
            for line in f:
                detector.feed(line)
                if detector.done:
                    break
        detector.close()
        encoding = detector.result['encoding'] or 'utf-8'
        
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
        
        if extension == '.md':
            # Basic conversion of markdown to plain text
            # For more complex needs, a more advanced library might be better
            html = markdown.markdown(content)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            return soup.get_text()
        return content

    elif extension == '.docx':
        doc = docx.Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)

    else:
        raise ValueError(f"Unsupported file type: {extension}")