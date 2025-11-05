"""ChromaDB manager for handling multiple collections."""
import os
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import chromadb
from chromadb.config import Settings
CHROMA_AVAILABLE = True

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
