"""Pure in-memory implementations of Cortex storage backends.

Used for:
- Test suite (fast, deterministic, no filesystem churn)
- Lambda cold-start caching (hold hot data in memory between invocations)
- Local development / notebooks

No external dependencies -- plain Python dicts and lists.
Thread-safe: all mutation and read-modify-write operations are protected by
threading.Lock, making these backends safe for concurrent Lambda warm-container
invocations sharing a module-level instance.
"""
import threading
import time
from typing import Any, Dict, List, Optional

from .base import KVBackend, STMBackend, VectorBackend


def _apply_filters(events: List[Dict], window_hours: int, filters: Dict) -> List[Dict]:
    """Filter a snapshot of events outside the lock (no mutual exclusion needed)."""
    cutoff = time.time() - window_hours * 3600
    f = filters or {}
    out = []
    for ev in events:
        ep = int(ev.get("epoch", 0) or 0)
        if ep < cutoff:
            continue
        if f.get("project") and ev.get("project") != f["project"]:
            continue
        if f.get("day"):
            ev_day = time.strftime("%Y-%m-%d", time.gmtime(ep))
            if ev_day != f["day"]:
                continue
        if f.get("session") and ev.get("session_id") != f["session"]:
            continue
        if f.get("intent") and ev.get("intent_class") != f["intent"]:
            continue
        out.append(ev)
    return out


class MemorySTMBackend(STMBackend):
    """In-memory event log. Events are lost when the process exits."""

    def __init__(self):
        self._events: List[Dict] = []
        self._lock = threading.Lock()
        self.path = None  # no filesystem path

    def append(self, event: dict) -> bool:
        if not isinstance(event, dict):
            return False
        with self._lock:
            self._events.append(dict(event))
        return True

    def fetch(self, window_hours: int = 72, filters: Optional[Dict] = None) -> List[Dict]:
        with self._lock:
            snapshot = list(self._events)
        return _apply_filters(snapshot, window_hours, filters or {})

    def prune(self, older_than_hours: int = 72) -> Dict:
        cutoff = time.time() - older_than_hours * 3600
        with self._lock:
            kept = [e for e in self._events if int(e.get("epoch", 0) or 0) >= cutoff]
            dropped = len(self._events) - len(kept)
            self._events = kept
        return {"kept": len(kept), "dropped": dropped}


class MemoryVectorBackend(VectorBackend):
    """In-memory vector store. No real embedding -- stores raw metadata only.

    Suitable for tests and Lambda hot-cache. Not for production semantic search:
    query_similar() returns distance=0.0 for all entries (no embeddings computed).
    """

    def __init__(self):
        self._entries: Dict[str, Dict] = {}  # id -> metadata
        self._docs: Dict[str, str] = {}      # id -> document text
        self._lock = threading.Lock()

    def get_all(self, filters: Optional[Dict] = None,
                include: Optional[List[str]] = None) -> Dict:
        with self._lock:
            ids = list(self._entries.keys())
            metas = [dict(self._entries[i]) for i in ids]
        if filters:
            filtered_ids = []
            filtered_metas = []
            for i, m in zip(ids, metas):
                if all(m.get(k) == v for k, v in filters.items()):
                    filtered_ids.append(i)
                    filtered_metas.append(m)
            ids, metas = filtered_ids, filtered_metas
        return {"ids": ids, "metadatas": metas}

    def update_metadata(self, ids: List[str], metadatas: List[Dict]) -> None:
        with self._lock:
            for doc_id, meta in zip(ids, metadatas):
                if doc_id in self._entries:
                    self._entries[doc_id].update(meta)
                else:
                    self._entries[doc_id] = dict(meta)

    def query_similar(self, text: str, k: int = 10) -> List[Dict]:
        """Return first k entries with distance=0.0.

        WARNING: distance=0.0 is a test stub, not a real semantic similarity score.
        This backend does not compute embeddings. Use FilesystemVectorBackend for
        production semantic search.
        """
        with self._lock:
            ids = list(self._entries.keys())[:k]
            snapshot = {i: dict(self._entries[i]) for i in ids}
        return [{"id": i, "metadata": snapshot[i], "distance": 0.0} for i in ids]

    def add(self, ids: List[str], documents: List[str],
            metadatas: List[Dict], embeddings=None) -> None:
        """Insert memories into the in-memory store."""
        with self._lock:
            for doc_id, doc, meta in zip(ids, documents, metadatas):
                self._entries[doc_id] = dict(meta)
                self._docs[doc_id] = doc

    def delete(self, ids: List[str]) -> None:
        """Remove memories by ID."""
        with self._lock:
            for doc_id in ids:
                self._entries.pop(doc_id, None)
                self._docs.pop(doc_id, None)

    def upsert(self, ids: List[str], documents: List[str],
               metadatas: List[Dict], embeddings=None) -> None:
        """Insert or replace memories. Deduplicates by ID."""
        with self._lock:
            for doc_id, doc, meta in zip(ids, documents, metadatas):
                self._entries[doc_id] = dict(meta)
                self._docs[doc_id] = doc


class MemoryKVBackend(KVBackend):
    """In-memory key-value store."""

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = value

    def incr(self, key: str, delta: int = 1) -> int:
        with self._lock:
            cur = int(self._store.get(key, 0))
            new = cur + delta
            self._store[key] = new
            return new
