"""
Vector Store Module using Chroma for semantic text storage and retrieval
"""
import os
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    chromadb = None
    Settings = None

import logging
logger = logging.getLogger(__name__)
class VectorStore:
    """
    Manages the Chroma vector database for semantic text storage and retrieval.
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
if __name__ == "__main__":
    # Test the VectorStore initialization
    import tempfile
    import shutil
    # Create a temporary directory for testing
    test_dir = tempfile.mkdtemp()
    try:
        # Test initialization
        vs = VectorStore(test_dir)
        print(f"✓ VectorStore initialized with persistence at {test_dir}")
        # Test collection creation
        collection = vs.create_collection("test_collection")
        print("✓ Collection created successfully")
        # Test adding texts
        texts = ["This is a test document about characters", "This is another document about settings"]
        metadatas = [{"source": "test1.txt", "type": "character"}, {"source": "test2.txt", "type": "setting"}]
        ids = ["doc1", "doc2"]
        vs.add_texts(texts, metadatas, ids)
        print("✓ Texts added successfully")
        # Test search
        results = vs.search("document about characters", n_results=2)
        print(f"✓ Search completed, found {len(results['ids'][0])} results")
    finally:
        # Clean up
        shutil.rmtree(test_dir)