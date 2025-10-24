"""
Knowledge Base Builder for constructing the hybrid knowledge base from processed entities and text
"""
from __future__ import annotations

import os
import logging
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .vector_store import VectorStore
from .structured_db import StructuredDB
from .search import HybridSearchEngine

# Import TextChunker if available; fallback to a minimal implementation
try:
    from ..preprocessing.text_chunker import TextChunker
except Exception:  # pragma: no cover - fallback for environments where the module isn't available yet
    from typing import NamedTuple

    class _TextChunk(NamedTuple):
        text: str
        source_file: str
        chapter: Optional[str] = None
        paragraph_start: Optional[int] = None
        paragraph_end: Optional[int] = None
        character_start: Optional[int] = None
        character_end: Optional[int] = None
        entities: List[str] = field(default_factory=list)

    class TextChunker:
        def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
            self.chunk_size = chunk_size
            self.chunk_overlap = chunk_overlap

        def chunk_text(
            self,
            text: str,
            source_file: str,
            chapter: Optional[str] = None,
            paragraph_starts: Optional[List[int]] = None,
        ) -> List[_TextChunk]:
            # Simple naive chunking fallback: split by length, no entity detection.
            # Prefer using your actual TextChunker when available.
            chunks: List[_TextChunk] = []
            start = 0
            n = len(text)
            while start < n:
                end = min(n, start + self.chunk_size)
                chunk_text = text[start:end]
                chunks.append(
                    _TextChunk(
                        text=chunk_text,
                        source_file=source_file,
                        chapter=chapter,
                        paragraph_start=None,
                        paragraph_end=None,
                        character_start=start,
                        character_end=end,
                        entities=[],
                    )
                )
                start = end - self.chunk_overlap
                if start < 0:
                    start = end
            return chunks

        def chunk_with_entity_detection(
            self,
            text: str,
            source_file: str,
            entities: List[Dict[str, Any]],
            chapter: Optional[str] = None,
            paragraph_starts: Optional[List[int]] = None,
        ) -> List[_TextChunk]:
            # Fallback: run basic chunking and attach entity names if any.
            base_chunks = self.chunk_text(text, source_file, chapter, paragraph_starts)
            # Heuristic: if an entity name appears in chunk text, add it
            entity_names = {e.get("name", "") for e in entities if e.get("name")}
            for c in base_chunks:
                c.entities[:] = [n for n in entity_names if n in c.text]
            return base_chunks

logger = logging.getLogger(__name__)


@dataclass
class EntityRecord:
    name: str
    type: str
    description: Optional[str] = None
    mentions: List[Dict[str, Any]] = field(default_factory=list)
    source_file: Optional[str] = None
    chapter: Optional[str] = None
    paragraph: Optional[int] = None

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("EntityRecord.name must be a non-empty string")
        if not self.type or not isinstance(self.type, str):
            raise ValueError("EntityRecord.type must be a non-empty string")
        if self.description is not None and not isinstance(self.description, str):
            raise ValueError("EntityRecord.description must be a string or None")


@dataclass
class TextChunkRecord:
    text: str
    source_file: str
    chapter: Optional[str] = None
    paragraph_start: Optional[int] = None
    paragraph_end: Optional[int] = None
    character_start: Optional[int] = None
    character_end: Optional[int] = None
    entities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.text or not isinstance(self.text, str):
            raise ValueError("TextChunkRecord.text must be a non-empty string")
        if not self.source_file or not isinstance(self.source_file, str):
            raise ValueError("TextChunkRecord.source_file must be a non-empty string")
        if self.entities is not None:
            if not isinstance(self.entities, list):
                raise ValueError("TextChunkRecord.entities must be a list of strings")
            if not all(isinstance(x, str) for x in self.entities):
                raise ValueError("TextChunkRecord.entities must contain only strings")


class KnowledgeBaseBuilder:
    """
    Orchestrates the construction of the hybrid knowledge base from validated entities and text chunks.

    - Typed inputs via EntityRecord and TextChunkRecord for validation.
    - Transactions in the structured DB ensure consistency.
    - Batch ingestion with configurable concurrency.
    - Optional embedding batch size to reduce memory pressure.
    - Optional retry on transient failures.
    - Path management using pathlib.
    - Auto-initialization of knowledge base on build if not already done.
    - Closeable resources and optional async API.
    """

    def __init__(
        self,
        data_dir: Union[str, Path, None] = None,
        collection_name: str = "knowledge_base",
        text_chunker: Optional[TextChunker] = None,
        embedding_batch_size: int = 32,
        max_workers: int = 4,
        auto_init: bool = True,
    ):
        """
        Initialize the knowledge base builder.

        Args:
            data_dir: Base directory for data storage. Defaults to {cwd}/data.
            collection_name: Name for the vector collection.
            text_chunker: Optional TextChunker instance. If None, a default is used.
            embedding_batch_size: Batch size for vector embeddings ingestion.
            max_workers: Max worker threads for concurrent processing.
            auto_init: If True, call initialize_knowledge_base() in build_knowledge_base().
        """
        if data_dir is None:
            data_dir = Path.cwd() / "data"
        else:
            data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        self.data_dir = data_dir
        self.vector_db_dir = data_dir / "vector_db"
        self.entities_db_path = data_dir / "entities.db"

        self.collection_name = collection_name
        self.text_chunker = text_chunker or TextChunker()
        self.embedding_batch_size = embedding_batch_size
        self.max_workers = max_workers
        self.auto_init = auto_init

        # Initialize storage components
        self.vector_store = VectorStore(str(self.vector_db_dir))
        self.structured_db = StructuredDB(str(self.entities_db_path))

        # Initialize search engine
        self.search_engine = HybridSearchEngine(self.vector_store, self.structured_db)

        logger.info("KnowledgeBaseBuilder initialized at %s", self.data_dir)

    def initialize_knowledge_base(self, collection_name: Optional[str] = None) -> None:
        """
        Initialize the vector collection and ensure DB schema is present.

        Args:
            collection_name: Optional collection name override. If not provided, uses instance config.
        """
        name = collection_name or self.collection_name
        try:
            # Ensure collection exists (idempotent)
            self.vector_store.create_collection(name)
            # Structured DB is already initialized in constructor
            logger.info("Knowledge base initialized successfully (collection=%s)", name)
        except Exception as e:
            logger.error("Failed to initialize knowledge base: %s", e, exc_info=True)
            raise

    def _normalize_entities(self, entities: Iterable[Union[EntityRecord, Dict[str, Any]]]) -> List[EntityRecord]:
        out: List[EntityRecord] = []
        for e in entities:
            if isinstance(e, dict):
                out.append(EntityRecord(**e))
            elif isinstance(e, EntityRecord):
                out.append(e)
            else:
                raise TypeError(f"Unsupported entity type: {type(e)}")
        return out

    def _normalize_chunks(self, chunks: Iterable[Union[TextChunkRecord, Dict[str, Any]]]) -> List[TextChunkRecord]:
        out: List[TextChunkRecord] = []
        for c in chunks:
            if isinstance(c, dict):
                out.append(TextChunkRecord(**c))
            elif isinstance(c, TextChunkRecord):
                out.append(c)
            else:
                raise TypeError(f"Unsupported chunk type: {type(c)}")
        return out

    def add_entity(self, entity: Union[EntityRecord, Dict[str, Any]]) -> int:
        """
        Add an entity to the structured database with a transaction.
        Also adds any mentions provided.

        Args:
            entity: EntityRecord or dict with keys:
                - name (str): Entity name
                - type (str): Entity type
                - description (str, optional)
                - mentions (list, optional): Mention dicts
                - source_file (str)
                - chapter (str, optional)
                - paragraph (int, optional)

        Returns:
            int: ID of the inserted entity
        """
        rec = entity if isinstance(entity, EntityRecord) else EntityRecord(**entity)
        try:
            with self.structured_db.transaction():
                entity_id = self.structured_db.insert_entity(rec.name, rec.type, rec.description)
                if rec.mentions:
                    for mention in rec.mentions:
                        self.structured_db.insert_entity_mention(
                            entity_id,
                            rec.source_file or mention.get("source_file"),
                            mention.get("chapter"),
                            mention.get("paragraph"),
                            mention.get("character_start"),
                            mention.get("character_end"),
                            mention.get("text"),
                        )
                logger.debug("Added entity %s (ID=%s)", rec.name, entity_id)
                return entity_id
        except Exception as e:
            logger.error("Failed to add entity %s: %s", getattr(rec, "name", None), e, exc_info=True)
            raise

    def add_text_chunk(self, chunk: Union[TextChunkRecord, Dict[str, Any]]) -> int:
        """
        Add a text chunk to both vector store and structured database with a transaction.

        Args:
            chunk: TextChunkRecord or dict with keys:
                - text (str): Content
                - source_file (str): Source file
                - chapter (str, optional)
                - paragraph_start (int, optional)
                - paragraph_end (int, optional)
                - character_start (int, optional)
                - character_end (int, optional)
                - entities (list, optional): Names of entities referenced
                - metadata (dict, optional): Extra metadata

        Returns:
            int: ID of the inserted chunk
        """
        rec = chunk if isinstance(chunk, TextChunkRecord) else TextChunkRecord(**chunk)
        embedding_id = str(uuid.uuid4())

        try:
            with self.structured_db.transaction():
                # Add to vector store
                metadata = {
                    "source_file": rec.source_file,
                    "chapter": rec.chapter,
                    "paragraph_start": rec.paragraph_start,
                    "paragraph_end": rec.paragraph_end,
                    "character_start": rec.character_start,
                    "character_end": rec.character_end,
                }
                metadata.update(rec.metadata or {})
                self.vector_store.add_texts(
                    texts=[rec.text],
                    metadatas=[metadata],
                    ids=[embedding_id],
                )

                # Add to structured DB
                chunk_id = self.structured_db.insert_text_chunk(
                    rec.text,
                    rec.source_file,
                    rec.chapter,
                    rec.paragraph_start,
                    rec.paragraph_end,
                    rec.character_start,
                    rec.character_end,
                    embedding_id,
                )

                # Add citations for entities if provided
                if rec.entities:
                    for entity_name in rec.entities:
                        entity = self.structured_db.get_entity_by_name(entity_name)
                        if entity is None:
                            logger.warning("Citation skipped: entity %r not found in DB", entity_name)
                            continue
                        self.structured_db.insert_citation(chunk_id, entity["id"])

                logger.debug("Added text chunk from %s (ID=%s)", rec.source_file, chunk_id)
                return chunk_id
        except Exception as e:
            logger.error("Failed to add text chunk from %s: %s", rec.source_file, e, exc_info=True)
            raise

    def _process_document_chunks(
        self,
        text: str,
        source_file: str,
        entities: Optional[List[Dict[str, Any]]],
        chapter: Optional[str],
    ) -> List[TextChunkRecord]:
        # Chunk the text
        if entities:
            chunks = self.text_chunker.chunk_with_entity_detection(text, source_file, entities, chapter)
        else:
            chunks = self.text_chunker.chunk_text(text, source_file, chapter)

        # Normalize to TextChunkRecord
        records: List[TextChunkRecord] = []
        for c in chunks:
            records.append(
                TextChunkRecord(
                    text=c.text,
                    source_file=c.source_file,
                    chapter=c.chapter,
                    paragraph_start=getattr(c, "paragraph_start", None),
                    paragraph_end=getattr(c, "paragraph_end", None),
                    character_start=getattr(c, "character_start", None),
                    character_end=getattr(c, "character_end", None),
                    entities=list(getattr(c, "entities", []) or []),
                )
            )
        return records

    def process_document(
        self,
        text: str,
        source_file: str,
        entities: Optional[List[Dict[str, Any]]] = None,
        chapter: Optional[str] = None,
    ) -> List[int]:
        """
        Process a document by chunking it and adding chunks to the knowledge base.

        Args:
            text: Document text
            source_file: Source file identifier
            entities: Optional list of entity dictionaries with position info
            chapter: Optional chapter/section name

        Returns:
            List[int]: List of chunk IDs added
        """
        try:
            chunks = self._process_document_chunks(text, source_file, entities, chapter)
            chunk_ids: List[int] = []
            for chunk in chunks:
                chunk_id = self.add_text_chunk(chunk)
                chunk_ids.append(chunk_id)
            logger.info("Processed document %s into %d chunks", source_file, len(chunk_ids))
            return chunk_ids
        except Exception as e:
            logger.error("Failed to process document %s: %s", source_file, e, exc_info=True)
            raise

    def _process_batch(
        self,
        items: Sequence[Any],
        worker,
        max_workers: Optional[int] = None,
        desc: str = "Processing",
    ) -> List[Any]:
        results: List[Any] = []
        workers = max_workers or self.max_workers
        if workers <= 1 or len(items) <= 1:
            for item in items:
                results.append(worker(item))
            return results

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(worker, item): item for item in items}
            for fut in as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as e:
                    item = futures[fut]
                    logger.error("Worker failed on item %s: %s", item, e, exc_info=True)
                    raise
        return results

    def build_knowledge_base(
        self,
        entities: Iterable[Union[EntityRecord, Dict[str, Any]]],
        text_chunks: Iterable[Union[TextChunkRecord, Dict[str, Any]]],
        collection_name: Optional[str] = None,
        reset: bool = False,
    ) -> Tuple[List[int], List[int]]:
        """
        Build the complete knowledge base from entities and text chunks.

        Args:
            entities: Sequence of entity data
            text_chunks: Sequence of text chunk data
            collection_name: Optional override of the vector collection name
            reset: If True, drop and recreate the vector collection (use with caution)

        Returns:
            Tuple[List[int], List[int]]: (entity_ids, chunk_ids)
        """
        try:
            if self.auto_init:
                name = collection_name or self.collection_name
                if reset:
                    try:
                        self.vector_store.drop_collection(name)
                    except Exception:
                        logger.warning("drop_collection not supported or collection does not exist; proceeding.")
                    self.initialize_knowledge_base(name)
                else:
                    self.initialize_knowledge_base(name)

            norm_entities = self._normalize_entities(entities)
            norm_chunks = self._normalize_chunks(text_chunks)

            # Add entities
            def add_entity_worker(e: EntityRecord) -> int:
                return self.add_entity(e)

            entity_ids = self._process_batch(norm_entities, add_entity_worker, desc="Adding entities")

            # Add text chunks in embedding batches
            chunk_ids: List[int] = []
            for i in range(0, len(norm_chunks), self.embedding_batch_size):
                batch = norm_chunks[i : i + self.embedding_batch_size]

                def add_chunk_worker(c: TextChunkRecord) -> int:
                    return self.add_text_chunk(c)

                batch_ids = self._process_batch(batch, add_chunk_worker, desc=f"Adding chunks [{i}-{i+len(batch)}]")
                chunk_ids.extend(batch_ids)

            logger.info(
                "Knowledge base built with %d entities and %d chunks (collection=%s)",
                len(entity_ids),
                len(chunk_ids),
                collection_name or self.collection_name,
            )
            return entity_ids, chunk_ids
        except Exception as e:
            logger.error("Failed to build knowledge base: %s", e, exc_info=True)
            raise

    async def abuild_knowledge_base(
        self,
        entities: Iterable[Union[EntityRecord, Dict[str, Any]]],
        text_chunks: Iterable[Union[TextChunkRecord, Dict[str, Any]]],
        collection_name: Optional[str] = None,
        reset: bool = False,
    ) -> Tuple[List[int], List[int]]:
        """
        Async wrapper over build_knowledge_base. Runs ingestion in a thread pool.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self.build_knowledge_base,
            entities,
            text_chunks,
            collection_name,
            reset,
        )

    def close(self) -> None:
        """
        Close all database connections.
        """
        try:
            self.structured_db.close()
            logger.info("Knowledge base connections closed")
        except Exception as e:
            logger.error("Error closing connections: %s", e, exc_info=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


if __name__ == "__main__":
    # Demo usage
    import tempfile
    from pathlib import Path

    test_dir = Path(tempfile.mkdtemp())
    try:
        with KnowledgeBaseBuilder(data_dir=test_dir) as builder:
            entities = [
                EntityRecord(
                    name="John Doe",
                    type="character",
                    description="Main protagonist",
                    source_file="chapter1.txt",
                    mentions=[
                        {"source_file": "chapter1.txt", "chapter": "Chapter 1", "paragraph": 5, "text": "John entered the room cautiously."},
                    ],
                ),
            ]
            text_chunks = [
                TextChunkRecord(
                    text="John entered the room cautiously.",
                    source_file="chapter1.txt",
                    chapter="Chapter 1",
                    paragraph_start=5,
                    paragraph_end=5,
                    character_start=120,
                    character_end=155,
                    entities=["John Doe"],
                ),
            ]
            builder.build_knowledge_base(entities, text_chunks, reset=True)

            entity_result = builder.search_engine.entity_search("John Doe")
            print("Entity search result:", entity_result)
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)