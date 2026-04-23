"""Abstract base classes for Cortex storage backends.

Three interfaces: STMBackend (event log), VectorBackend (semantic store),
KVBackend (key-value counters and thresholds).

External packages register implementations via entry_points or direct call
to register_backend() in cortex.backends.__init__.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class STMBackend(ABC):
    """Append-only 72h event log."""

    @abstractmethod
    def append(self, event: dict) -> bool:
        """Append event. Returns True if written, False if filtered/deduped."""

    @abstractmethod
    def fetch(self, window_hours: int = 72, filters: Optional[Dict] = None) -> List[Dict]:
        """Return events within window, applying optional filters.

        filters keys: project, day (YYYY-MM-DD), session, intent.
        """

    @abstractmethod
    def prune(self, older_than_hours: int = 72) -> Dict:
        """Drop events older than window. Returns {"kept": int, "dropped": int}."""

    def close(self) -> None:
        """Flush and disconnect. Default no-op for simple backends."""


class VectorBackend(ABC):
    """Semantic vector store -- powers Dream maintenance steps."""

    @abstractmethod
    def get_all(self, filters: Optional[Dict] = None,
                include: Optional[List[str]] = None) -> Dict:
        """Return metadata (and optionally other fields) for stored entries.

        Returns dict with keys "ids", "metadatas" (and whatever include specifies).
        """

    @abstractmethod
    def update_metadata(self, ids: List[str], metadatas: List[Dict]) -> None:
        """Batch-update metadata for given IDs."""

    @abstractmethod
    def query_similar(self, text: str, k: int = 10) -> List[Dict]:
        """Return top-k most similar entries as list of {id, metadata, distance}."""


class KVBackend(ABC):
    """Small key-value store for thresholds, counters, epochs."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Return value for key, or None if absent."""

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set key to value."""

    @abstractmethod
    def incr(self, key: str, delta: int = 1) -> int:
        """Increment integer value by delta. Creates key with value=delta if absent."""
