# George - Standalone AI Assistant for Authors

A local-first AI assistant designed specifically for authors and world-builders. George helps you:

- Import and process manuscripts in multiple formats (.docx, .md, .txt)
- Extract and validate entities (characters, places, organizations)
- Build hybrid knowledge bases for your fictional worlds
- Provide contextual chat assistance with citations

## Features

- **Document Processing**: Multi-format document parser supporting Word, Markdown, and plain text
- **Entity Extraction**: Advanced NLP-powered entity recognition using spaCy
- **Knowledge Base**: Hybrid vector + structured database for storing and retrieving information
- **Local-First**: All processing happens locally, no cloud dependencies
- **Web Interface**: Flask-based UI for easy interaction

## Installation

### Prerequisites

- Python 3.8 or higher
- spaCy English model: `python -m spacy download en_core_web_sm`

### Install

```bash
pip install -e .
```

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

## Quick Start

1. **Run the complete workflow** (import → extract → validate → build KB):
   ```bash
   python george.py --mode workflow --file path/to/your/manuscript.docx
   ```

2. **Start the web interface**:
   ```bash
   python george.py --mode chat
   ```
   Then open http://localhost:5000 in your browser.

3. **Import a manuscript only**:
   ```bash
   python george.py --mode import --file path/to/your/manuscript.md
   ```

## Usage

### Command Line Options

```bash
usage: george.py [-h] [--mode {import,validate,build,chat,workflow}] 
                 [--file FILE] [--host HOST] [--port PORT] [--project PROJECT]

Standalone George - Local-first AI assistant for authors

optional arguments:
  -h, --help            show this help message and exit
  --mode {import,validate,build,chat,workflow}
                        Operation mode (default: workflow)
  --file FILE           Path to manuscript file for import
  --host HOST           Host for chat interface (default: 0.0.0.0)
  --port PORT           Port for chat interface (default: 5000)
  --project PROJECT     Project directory path
```

### Operation Modes

- **import**: Parse and process a manuscript file
- **validate**: Review and validate extracted entities
- **build**: Build the knowledge base from validated entities
- **chat**: Start the web-based chat interface
- **workflow**: Complete pipeline (import → validate → build → ready for chat)

## Project Structure

```
george/
├── src/george/           # Main package
│   ├── core.py          # Main orchestrator
│   ├── parsers/         # Document parsing
│   ├── preprocessing/   # Text processing
│   ├── akg/             # Automatic Knowledge Generation
│   │   ├── core/        # Entity extraction
│   │   └── validation/  # Entity validation
│   ├── knowledge_base/  # Hybrid KB storage
│   └── ui/              # Web interface
├── tests/               # Test suite
├── docs/                # Documentation
├── examples/            # Example scripts
├── data/                # Data storage
└── config/              # Configuration files
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black src/ tests/
```

### Type Checking

```bash
mypy src/
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

For more detailed documentation, see the `docs/` directory.