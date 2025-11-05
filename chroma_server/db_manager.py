"""ChromaDB manager for handling multiple collections."""
import os
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import json

import networkx as nx
from networkx.readwrite import json_graph

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except (ImportError, Exception) as e:
    CHROMA_AVAILABLE = False
    logging.warning(f"ChromaDB import failed: {e}. Vector storage will be disabled.")

logger = logging.getLogger(__name__)

class ChromaManager:
    """Manages multiple ChromaDB collections."""
    def __init__(self, persist_directory: Union[str, Path] = None):
        if not CHROMA_AVAILABLE:
            logger.warning("ChromaDB is not available. Vector storage disabled.")
            self.client = None
            return
            
        if persist_directory is None:
            persist_directory = Path.cwd() / "data" / "chroma_db"
        else:
            persist_directory = Path(persist_directory)
        
        persist_directory.mkdir(parents=True, exist_ok=True)
        
        try:
            self.client = chromadb.PersistentClient(
                path=str(persist_directory),
                settings=Settings(anonymized_telemetry=False, allow_reset=True)
            )
            logger.info(f"ChromaDB manager initialized at {persist_directory}")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}", exc_info=True)
            self.client = None

    def get_or_create_collection(self, name: str) -> Optional[Any]:
        if not self.client:
            return None
        try:
            return self.client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
        except Exception as e:
            logger.error(f"Failed to get or create collection {name}: {e}", exc_info=True)
            return None

    def add_texts(self, collection_name: str, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None, ids: Optional[List[str]] = None) -> None:
        collection = self.get_or_create_collection(collection_name)
        if not collection:
            raise ValueError(f"Could not get or create collection: {collection_name}")
        
        if not texts:
            return
            
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
            
        if metadatas is None:
            metadatas = [{} for _ in texts]
            
        try:
            collection.add(documents=texts, metadatas=metadatas, ids=ids)
            logger.debug(f"Added {len(texts)} texts to collection '{collection_name}'")
        except Exception as e:
            logger.error(f"Failed to add texts to collection {collection_name}: {e}", exc_info=True)
            raise

    def query(self, collection_name: str, query_texts: List[str], n_results: int = 5, where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        collection = self.get_or_create_collection(collection_name)
        if not collection:
            raise ValueError(f"Could not get or create collection: {collection_name}")
            
        try:
            return collection.query(query_texts=query_texts, n_results=n_results, where=where)
        except Exception as e:
            logger.error(f"Failed to query collection {collection_name}: {e}", exc_info=True)
            raise

# ===== Consolidated Knowledge Base Logic (moved from src/george/knowledge_base) =====
# VectorStore, StructuredDB, HybridSearchEngine, KnowledgeBaseBuilder

import sqlite3


class StructuredDB:
    """SQLite-backed structured store for entities, mentions, chunks, citations, and notes."""
    def __init__(self, db_path: Union[str, Path] = None):
        if db_path is None:
            db_path = Path.cwd() / "data" / "entities.db"
        else:
            db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.initialize_database()

    def initialize_database(self) -> None:
        c = self.conn.cursor()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS entities (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT UNIQUE NOT NULL,
              type TEXT NOT NULL,
              description TEXT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS entity_mentions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              entity_id INTEGER NOT NULL,
              source_file TEXT NOT NULL,
              chapter TEXT,
              paragraph INTEGER,
              character_start INTEGER,
              character_end INTEGER,
              mention_text TEXT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS text_chunks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chunk_text TEXT NOT NULL,
              source_file TEXT NOT NULL,
              chapter TEXT,
              paragraph_start INTEGER,
              paragraph_end INTEGER,
              character_start INTEGER,
              character_end INTEGER,
              embedding_id TEXT UNIQUE,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS citations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chunk_id INTEGER NOT NULL,
              entity_id INTEGER NOT NULL,
              relationship_type TEXT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (chunk_id) REFERENCES text_chunks (id) ON DELETE CASCADE,
              FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE,
              UNIQUE(chunk_id, entity_id)
            );
            CREATE TABLE IF NOT EXISTS entity_notes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              entity_id INTEGER NOT NULL,
              user_id TEXT NOT NULL,
              note_text TEXT NOT NULL,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS chat_summaries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              original_question TEXT,
              summary_text TEXT NOT NULL,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
            CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON text_chunks(embedding_id);
            CREATE INDEX IF NOT EXISTS idx_citations_chunk ON citations(chunk_id);
            CREATE INDEX IF NOT EXISTS idx_citations_entity ON citations(entity_id);
            CREATE INDEX IF NOT EXISTS idx_entity_notes_entity ON entity_notes(entity_id);
            CREATE INDEX IF NOT EXISTS idx_chat_summaries_user ON chat_summaries(user_id);
            CREATE INDEX IF NOT EXISTS idx_chat_summaries_project ON chat_summaries(project_id);
            """
        )

    def transaction(self):
        class _Tx:
            def __init__(self, conn):
                self.conn = conn
                self._nested = False
            def __enter__(self):
                if self.conn.in_transaction:
                    self._nested = True
                    return self
                self.conn.execute("BEGIN")
                return self
            def __exit__(self, exc_type, *_):
                if self._nested:
                    return
                if exc_type is None:
                    self.conn.commit()
                else:
                    self.conn.rollback()
        return _Tx(self.conn)

    def insert_entity(self, name: str, entity_type: str, description: Optional[str] = None) -> int:
        c = self.conn.cursor()
        c.execute("INSERT OR IGNORE INTO entities (name, type, description) VALUES (?, ?, ?)", (name, entity_type, description))
        if c.rowcount > 0:
            return c.lastrowid
        c.execute("SELECT id FROM entities WHERE name = ?", (name,))
        row = c.fetchone()
        return row[0] if row else 0

    def insert_entity_mention(self, entity_id: int, source_file: str, chapter: Optional[str] = None,
                               paragraph: Optional[int] = None, character_start: Optional[int] = None,
                               character_end: Optional[int] = None, mention_text: Optional[str] = None) -> int:
        c = self.conn.cursor()
        c.execute(
            """
            INSERT INTO entity_mentions (entity_id, source_file, chapter, paragraph, character_start, character_end, mention_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (entity_id, source_file, chapter, paragraph, character_start, character_end, mention_text),
        )
        return c.lastrowid

    def insert_text_chunk(self, chunk_text: str, source_file: str, chapter: Optional[str] = None,
                           paragraph_start: Optional[int] = None, paragraph_end: Optional[int] = None,
                           character_start: Optional[int] = None, character_end: Optional[int] = None,
                           embedding_id: Optional[str] = None) -> int:
        c = self.conn.cursor()
        c.execute(
            """
            INSERT INTO text_chunks (chunk_text, source_file, chapter, paragraph_start, paragraph_end, character_start, character_end, embedding_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chunk_text, source_file, chapter, paragraph_start, paragraph_end, character_start, character_end, embedding_id),
        )
        return c.lastrowid

    def insert_citation(self, chunk_id: int, entity_id: int, relationship_type: Optional[str] = None) -> int:
        c = self.conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO citations (chunk_id, entity_id, relationship_type) VALUES (?, ?, ?)",
            (chunk_id, entity_id, relationship_type),
        )
        return c.lastrowid

    def get_entity_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM entities WHERE name = ?", (name,))
        row = c.fetchone()
        return dict(row) if row else None


class VectorStore:
    """
    Manages the Chroma vector database for semantic text storage and retrieval.
    Enhanced version with full functionality.
    """
    def __init__(self, persist_directory: str = None):
        """
        Initialize the vector store with Chroma client.
        Args:
            persist_directory (str): Path to persist the vector database
        """
        if not CHROMA_AVAILABLE:
            logger.warning("ChromaDB is not available. Vector storage disabled.")
            self.client = None
            self.collection = None
            return
            
        if persist_directory is None:
            persist_directory = os.path.join(os.getcwd(), "data", "vector_db")
        
        # Create the directory if it doesn't exist
        os.makedirs(persist_directory, exist_ok=True)
        
        try:
            # Initialize Chroma client with persistence
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(
                    anonymized_telemetry=False
                )
            )
            self.collection = None
            logger.info(f"Vector store initialized with directory: {persist_directory}")
        except Exception as e:
            logger.warning(f"Failed to initialize ChromaDB: {e}. Vector storage disabled.")
            self.client = None
            self.collection = None
        
        self.persist_directory = persist_directory
    
    def create_collection(self, name: str = "knowledge_base"):
        """
        Create or get a collection in the vector database.
        Args:
            name (str): Name of the collection
        Returns:
            Collection: Chroma collection object
        """
        if self.client is None:
            logger.warning("ChromaDB client not available. Cannot create collection.")
            return None
            
        try:
            self.collection = self.client.create_collection(name=name)
            logger.info(f"Created new collection: {name}")
        except Exception as e:
            logger.warning(f"Collection {name} might already exist: {e}")
            self.collection = self.client.get_collection(name=name)
            logger.info(f"Retrieved existing collection: {name}")
        return self.collection
    
    def get_collection(self, name: str = "knowledge_base"):
        """
        Get an existing collection.
        Args:
            name (str): Name of the collection
        Returns:
            Collection: Chroma collection object
        """
        try:
            self.collection = self.client.get_collection(name=name)
            logger.info(f"Retrieved collection: {name}")
        except Exception as e:
            logger.error(f"Failed to get collection {name}: {e}")
            raise
        return self.collection
    
    def add_texts(self, texts, metadatas=None, ids=None):
        """
        Add texts to the vector store.
        Args:
            texts (list): List of text strings to embed and store
            metadatas (list, optional): List of metadata dictionaries
            ids (list, optional): List of IDs for the texts
        """
        if self.collection is None:
            raise ValueError("No collection initialized. Call create_collection() first.")
        try:
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Added {len(texts)} texts to collection")
        except Exception as e:
            logger.error(f"Failed to add texts to collection: {e}")
            raise
    
    def search(self, query_text, n_results=5):
        """
        Search for similar texts using semantic similarity.
        Args:
            query_text (str): Text to search for
            n_results (int): Number of results to return
        Returns:
            dict: Search results with documents, metadatas, and distances
        """
        if self.collection is None:
            raise ValueError("No collection initialized. Call create_collection() first.")
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            logger.info(f"Search returned {len(results['ids'][0])} results")
            return results
        except Exception as e:
            logger.error(f"Failed to search collection: {e}")
            raise


class HybridSearchEngine:
    def __init__(self, vector_store: VectorStore, structured_db: StructuredDB):
        self.vector_store = vector_store
        self.structured_db = structured_db

    def entity_search(self, entity_name: str) -> Optional[Dict[str, Any]]:
        return self.structured_db.get_entity_by_name(entity_name)

    def semantic_search(self, query: str, n_results: int = 5, collection: Optional[str] = None) -> Dict[str, Any]:
        return self.vector_store.search(query, n_results, collection)

    def hybrid_search(self, query: str, n_results: int = 5, collection: Optional[str] = None) -> Dict[str, Any]:
        sem = self.semantic_search(query, n_results, collection)
        return {"semantic_results": sem, "entity_results": []}


class GraphManager:
    """Manages NetworkX graphs for each project."""
    def __init__(self, persist_directory: Union[str, Path] = None):
        if persist_directory is None:
            persist_directory = Path.cwd() / "data" / "graph_db"
        else:
            persist_directory = Path(persist_directory)

        persist_directory.mkdir(parents=True, exist_ok=True)
        self.persist_directory = persist_directory
        self.graphs = {}  # In-memory cache
        logger.info(f"GraphManager initialized at {self.persist_directory}")

    def _get_graph_path(self, project_id: str) -> Path:
        """Gets the file path for a project's graph."""
        return self.persist_directory / f"{project_id}_graph.json"

    def get_or_create_graph(self, project_id: str) -> nx.Graph:
        """Loads a graph from disk or creates a new one."""
        if project_id in self.graphs:
            return self.graphs[project_id]

        graph_path = self._get_graph_path(project_id)
        if graph_path.exists():
            try:
                with open(graph_path, 'r') as f:
                    data = json.load(f)
                    g = json_graph.node_link_graph(data)
                self.graphs[project_id] = g
                logger.info(f"Loaded graph for {project_id} from disk.")
                return g
            except Exception as e:
                logger.error(f"Failed to load graph {project_id}: {e}. Creating new one.")

        g = nx.Graph()
        self.graphs[project_id] = g
        logger.info(f"Created new in-memory graph for {project_id}.")
        return g

    def save_graph(self, project_id: str):
        """Saves a graph from memory to a JSON file on disk."""
        if project_id not in self.graphs:
            logger.warning(f"No graph in memory for {project_id} to save.")
            return

        g = self.graphs[project_id]
        graph_path = self._get_graph_path(project_id)
        try:
            data = json_graph.node_link_data(g)
            with open(graph_path, 'w') as f:
                json.dump(data, f)
            logger.info(f"Successfully saved graph for {project_id} to disk.")
        except Exception as e:
            logger.error(f"Failed to save graph {project_id}: {e}")

    def add_node(self, project_id: str, node_id: str, **attrs):
        """Adds a node with attributes to the project graph."""
        g = self.get_or_create_graph(project_id)
        g.add_node(node_id, **attrs)

    def add_edge(self, project_id: str, node_from: str, node_to: str, **attrs):
        """Adds an edge with attributes between two nodes."""
        g = self.get_or_create_graph(project_id)
        g.add_edge(node_from, node_to, **attrs)
