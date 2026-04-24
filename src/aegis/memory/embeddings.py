"""Embedding functions for ChromaDB."""

from __future__ import annotations

from ..utils.logging import get_logger

logger = get_logger(__name__)


def get_embedding_function(model_name: str = "all-MiniLM-L6-v2") -> object:
    """Get embedding function for ChromaDB.

    Tries SentenceTransformer first, falls back to Chroma's default.
    """
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        ef = SentenceTransformerEmbeddingFunction(model_name=model_name)
        logger.info("Using SentenceTransformer embeddings", model=model_name)
        return ef
    except Exception as e:
        logger.warning("SentenceTransformer unavailable, using default embeddings", error=str(e))
        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            return DefaultEmbeddingFunction()
        except Exception:
            return None
