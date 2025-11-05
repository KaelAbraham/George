"""
Vector Store Module using Chroma for semantic text storage and retrieval
"""
import os
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    chromadb = None
    Settings = None

logger = logging.getLogger(__name__)

class VectorStore:
    """
    Manages the Chroma vector database for semantic text storage and retrieval.
    
    - Uses UUIDs for document IDs to prevent collisions
    - Provides transaction-safe collection management
    - Handles graceful degradation when Chroma isn't available
    - Supports batch operations for performance
    """
    def __init__(self, persist_directory: Union[str, Path] = None):
        """
        Initialize the vector store with Chroma client.
        
        Args:
            persist_directory: Path to persist the vector database
        """
        if not CHROMA_AVAILABLE:
            logger.warning("ChromaDB is not available. Vector storage disabled.")
            self.client = None
            self.collection = None
            return
            
        if persist_directory is None:
            persist_directory = Path.cwd() / "data" / "vector_db"
        else:
            persist_directory = Path(persist_directory)
        
        persist_directory.mkdir(parents=True, exist_ok=True)
        
        try:
            # Initialize Chroma client with persistence
            self.client = chromadb.PersistentClient(
                path=str(persist_directory),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            self.collection = None
            logger.info(f"Vector store initialized at {persist_directory}")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}", exc_info=True)
            self.client = None
            self.collection = None
            
        self.persist_directory = persist_directory

    def create_collection(self, name: str = "knowledge_base") -> bool:
        """
        Create or get a collection in the vector database.
        
        Args:
            name: Name of the collection
            
        Returns:
            bool: True if collection was created, False if it existed
        """
        if not self.client:
            return False
            
        try:
            # Check if collection exists
            existing = self.client.list_collections()
            if any(c.name == name for c in existing):
                self.collection = self.client.get_collection(name=name)
                logger.debug(f"Using existing collection: {name}")
                return False
            
            # Create new collection
            self.collection = self.client.create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Created new collection: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create collection {name}: {e}", exc_info=True)
            raise

    def drop_collection(self, name: str = "knowledge_base") -> None:
        """
        Drop a collection from the vector database.
        
        Args:
            name: Name of the collection to drop
        """
        if not self.client:
            return
            
        try:
            if any(c.name == name for c in self.client.list_collections()):
                self.client.delete_collection(name=name)
                logger.info(f"Dropped collection: {name}")
            else:
                logger.debug(f"Collection {name} does not exist")
        except Exception as e:
            logger.error(f"Failed to drop collection {name}: {e}", exc_info=True)
            raise

    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> None:
        """
        Add texts to the vector store with batch support.
        
        Args:
            texts: List of text strings to embed and store
            metadatas: List of metadata dictionaries
            ids: List of IDs for the texts (if None, UUIDs are generated)
        """
        if not self.collection:
            raise ValueError("No collection initialized. Call create_collection() first.")
            
        if not texts:
            return
            
        # Generate unique IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
            
        # Prepare metadata if not provided
        if metadatas is None:
            metadatas = [{} for _ in texts]
            
        try:
            # Chroma expects all arguments to be the same length
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            logger.debug(f"Added {len(texts)} texts to vector store")
        except Exception as e:
            logger.error(f"Failed to add texts to vector store: {e}", exc_info=True)
            raise

    def search(
        self,
        query_texts: List[str],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Search for similar texts using semantic similarity.
        
        Args:
            query_texts: List of texts to search for
            n_results: Number of results to return per query
            where: Optional metadata filter
            
        Returns:
            dict: Search results with documents, metadatas, and distances
        """
        if not self.collection:
            raise ValueError("No collection initialized. Call create_collection() first.")
            
        try:
            results = self.collection.query(
                query_texts=query_texts,
                n_results=n_results,
                where=where
            )
            logger.debug(f"Search returned {len(results['ids'][0])} results per query")
            return results
        except Exception as e:
            logger.error(f"Failed to search vector store: {e}", exc_info=True)
            raise

    def close(self) -> None:
        """Close the vector store connection."""
        if self.client:
            try:
                # Chroma doesn't have a close method, but we can clear resources
                self.client = None
                self.collection = None
                logger.info("Vector store connection closed")
            except Exception as e:
                logger.error(f"Error closing vector store: {e}", exc_info=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()