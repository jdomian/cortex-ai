"""Embedder ABC -- pluggable text-to-vector interface.

All embedder implementations must subclass Embedder and implement
embed_one, embed_batch, dimension, and model_id.
"""
from abc import ABC, abstractmethod
from typing import List


class Embedder(ABC):
    """Abstract base class for text embedding backends."""

    @abstractmethod
    def embed_one(self, text: str) -> List[float]:
        """Embed a single text string. Returns a float vector."""

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of strings. Returns a list of float vectors."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension produced by this embedder."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Canonical model identifier (e.g. 'all-MiniLM-L6-v2')."""
