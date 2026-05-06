"""Abstract base classes for Cortex storage backends.

Three interfaces: STMBackend (event log), VectorBackend (semantic store),
KVBackend (key-value counters and thresholds).

External packages register implementations via entry_points or direct call
to register_backend() in cortex.backends.__init__.
"""
import time
import uuid
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class LockLease:
    """Returned by KVBackend.acquire_lock() on success.

    Holds the lease token and provides convenience methods for renewing/releasing
    without holding a reference to the backend explicitly.
    """
    key: str
    token: str
    expires_at: float
    _backend: Any  # KVBackend, typed as Any to avoid circular ref

    def renew(self, ttl_sec: int = None) -> bool:
        """Renew this lease. Returns True if the lease was still held."""
        ttl = ttl_sec if ttl_sec is not None else max(10, int(self.expires_at - time.time()))
        return self._backend.renew_lock(self.key, self.token, ttl)

    def release(self) -> bool:
        """Release this lease. Returns True if successfully released."""
        return self._backend.release_lock(self.key, self.token)


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

    @abstractmethod
    def add(self, ids: List[str], documents: List[str],
            metadatas: List[Dict], embeddings: Optional[List[List[float]]] = None) -> None:
        """Insert memories into the store.

        Args:
            ids: unique identifiers for each document
            documents: raw text content for each entry
            metadatas: metadata dicts (one per document)
            embeddings: optional pre-computed embeddings; if None, the backend
                generates them via its configured embedding function
        """

    @abstractmethod
    def delete(self, ids: List[str]) -> None:
        """Remove memories by ID."""

    @abstractmethod
    def upsert(self, ids: List[str], documents: List[str],
               metadatas: List[Dict], embeddings: Optional[List[List[float]]] = None) -> None:
        """Insert or replace memories. Deduplicates by ID.

        Args:
            ids: unique identifiers (existing IDs are replaced, new ones are inserted)
            documents: raw text content for each entry
            metadatas: metadata dicts (one per document)
            embeddings: optional pre-computed embeddings
        """

    def close(self) -> None:
        """Default no-op. Backends with persistent connections override."""


class KVBackend(ABC):
    """Small key-value store for thresholds, counters, epochs.

    Locking API (v0.7.0): opt-in via supports_locking(). Backends that return
    False from supports_locking() may leave the locking methods unimplemented.
    Callers must check supports_locking() before invoking the lock API.

    Deprecation notice: KVBackend subclasses that do not override supports_locking()
    will emit a DeprecationWarning starting in v0.7.0. The lock API will become
    mandatory in v1.0.
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Return value for key, or None if absent."""

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set key to value."""

    @abstractmethod
    def incr(self, key: str, delta: int = 1) -> int:
        """Increment integer value by delta. Creates key with value=delta if absent."""

    # ------------------------------------------------------------------
    # Locking capability (additive surface, not abstract in v0.7.0)
    # ------------------------------------------------------------------

    def supports_locking(self) -> bool:
        """Return True if this backend implements the lock API.

        Third-party backends written against v0.6.x return False by default.
        Override and return True once acquire_lock, renew_lock, release_lock
        are implemented. The default will emit a DeprecationWarning in a future
        release to encourage adoption before v1.0 makes locking mandatory.
        """
        return False

    def acquire_lock(self, key: str, ttl_sec: int) -> Optional["LockLease"]:
        """Acquire an exclusive lock on key for up to ttl_sec seconds.

        Returns a LockLease on success, None if the lock is already held.
        Only valid when supports_locking() returns True.

        Args:
            key: lock key namespace (e.g. "dream.run")
            ttl_sec: max hold time in seconds; lock auto-expires after this
        """
        if not self.supports_locking():
            raise NotImplementedError(
                f"{type(self).__name__}.acquire_lock() called but supports_locking() "
                "returned False. Override supports_locking() and implement the lock API."
            )
        raise NotImplementedError(
            f"{type(self).__name__} advertises supports_locking()=True but "
            "did not implement acquire_lock()."
        )

    def renew_lock(self, key: str, token: str, ttl_sec: int) -> bool:
        """Renew an existing lock lease. Returns True if the token matched and renewed."""
        if not self.supports_locking():
            raise NotImplementedError(
                f"{type(self).__name__}.renew_lock() called but supports_locking() "
                "returned False."
            )
        raise NotImplementedError(
            f"{type(self).__name__} advertises supports_locking()=True but "
            "did not implement renew_lock()."
        )

    def release_lock(self, key: str, token: str) -> bool:
        """Release a lock lease. Returns True if the token matched and was released."""
        if not self.supports_locking():
            raise NotImplementedError(
                f"{type(self).__name__}.release_lock() called but supports_locking() "
                "returned False."
            )
        raise NotImplementedError(
            f"{type(self).__name__} advertises supports_locking()=True but "
            "did not implement release_lock()."
        )
