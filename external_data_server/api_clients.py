import requests
import wikipediaapi
from datamuse import datamuse
import logging

logger = logging.getLogger(__name__)

class ExternalAPIs:
    """
    Wraps all external, vetted data sources.
    Ensures all output is sanitized, cited plain text.
    """
    
    def __init__(self):
        # Initialize Wikipedia API
        self.wiki = wikipediaapi.Wikipedia(
            language='en',
            extract_format=wikipediaapi.ExtractFormat.WIKI,
            user_agent='CaudexPro/1.0 (hello@caudex.pro)'
        )
        # Initialize Wiktionary
        self.wiktionary = wikipediaapi.Wikipedia(
            language='en',
            extract_format=wikipediaapi.ExtractFormat.WIKI,
            # We must specify the custom API URL for Wiktionary
            url='https://en.wiktionary.org/w/api.php',
            user_agent='CaudexPro/1.0 (hello@caudex.pro)'
        )
        # Initialize Datamuse
        self.datamuse = datamuse.Datamuse()

    def _sanitize_and_cite(self, text: str, source: str) -> str:
        """Strips newlines and adds the unremoveable citation tag."""
        if not text:
            return ""
        # Remove extra whitespace and newlines that confuse LLMs
        text = ' '.join(text.split())
        return f"[Source: {source}]\n{text}\n\n"

    def get_wikipedia(self, query: str) -> str:
        """Fetches the summary from Wikipedia."""
        try:
            page = self.wiki.page(query)
            if page.exists():
                # Get the first 300 words as a summary, ending at a period.
                summary = page.summary[0:page.summary.find('.', 300) + 1]
                if not summary or len(summary) < 20:
                    summary = page.text.split('\n')[0] # Fallback to first line
                
                return self._sanitize_and_cite(summary, f"wikipedia.org/wiki/{page.title.replace(' ', '_')}")
            return ""
        except Exception as e:
            logger.error(f"Wikipedia query failed: {e}")
            return ""

    def get_wiktionary(self, query: str) -> str:
        """Fetches the definition from Wiktionary."""
        try:
            page = self.wiktionary.page(query)
            if page.exists():
                # Wiktionary text is complex, find the first 'Etymology' or 'Noun' line
                lines = page.text.split('\n')
                definition = ""
                for line in lines:
                    if line.startswith('===') or line.startswith('=='): # Skip headers
                        continue
                    if line.strip():
                        # Find the first definition, often marked with '#'
                        if line.startswith('# '):
                            definition = line.lstrip('# ')
                            break
                
                if not definition and lines: # Fallback if no '#' found
                    definition = lines[0]

                return self._sanitize_and_cite(definition, f"en.wiktionary.org/wiki/{page.title.replace(' ', '_')}")
            return ""
        except Exception as e:
            logger.error(f"Wiktionary query failed: {e}")
            return ""

    def get_datamuse_rhymes(self, query: str) -> str:
        """Gets rhyming words from Datamuse."""
        try:
            results = self.datamuse.words(rel_rhy=query, max=15)
            words = [r['word'] for r in results]
            if not words:
                return ""
            return self._sanitize_and_cite(f"Rhymes for '{query}': {', '.join(words)}", "Datamuse API (datamuse.com)")
        except Exception as e:
            logger.error(f"Datamuse query failed: {e}")
            return ""
            
    def get_datamuse_synonyms(self, query: str) -> str:
        """Gets synonyms (words that mean like) from Datamuse."""
        try:
            results = self.datamuse.words(ml=query, max=15)
            words = [r['word'] for r in results]
            if not words:
                return ""
            return self._sanitize_and_cite(f"Synonyms/related words for '{query}': {', '.join(words)}", "Datamuse API (datamuse.com)")
        except Exception as e:
            logger.error(f"Datamuse query failed: {e}")
            return ""