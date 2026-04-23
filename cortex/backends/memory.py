"""Pure in-memory implementations of Cortex storage backends.

Used for:
- Test suite (fast, deterministic, no filesystem churn)
- Lambda cold-start caching (hold hot data in memory between invocations)
- Local development / notebooks

No external dependencies -- plain Python dicts and lists.
"""
import time
from typing import Any, Dict, List, Optional

from .base import KVBackend, STMBackend, VectorBackend


class MemorySTMBackend(STMBackend):
    """In-memory event log. Events are lost when the process exits."""

    def __init__(self):
        self._events: List[Dict] = []
        self.path = None  # no filesystem path

    def append(self, event: dict) -> bool:
        if not isinstance(event, dict):
            return False
        self._events.append(dict(event))
        return True

    def fetch(self, window_hours: int = 72, filters: Optional[Dict] = None) -> List[Dict]:
        cutoff = time.time() - window_hours * 3600
        f = filters or {}
        out = []
        for ev in self._events:
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

    def prune(self, older_than_hours: int = 72) -> Dict:
        cutoff = time.time() - older_than_hours * 3600
        kept = []
        dropped = 0
        for ev in self._events:
            ep = int(ev.get("epoch", 0) or 0)
            if ep < cutoff:
                dropped += 1
            else:
                kept.append(ev)
        self._events = kept
        return {"kept": len(kept), "dropped": dropped}


class MemoryVectorBackend(VectorBackend):
    """In-memory vector store. No real embedding -- stores raw metadata only."""

    def __init__(self):
        self._entries: Dict[str, Dict] = {}  # id -> metadata

    def get_all(self, filters: Optional[Dict] = None,
                include: Optional[List[str]] = None) -> Dict:
        ids = list(self._entries.keys())
        metas = [self._entries[i] for i in ids]
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
        for doc_id, meta in zip(ids, metadatas):
            if doc_id in self._entries:
                self._entries[doc_id].update(meta)
            else:
                self._entries[doc_id] = dict(meta)

    def query_similar(self, text: str, k: int = 10) -> List[Dict]:
        # No real embeddings -- return first k entries
        ids = list(self._entries.keys())[:k]
        return [{"id": i, "metadata": self._entries[i], "distance": 0.0} for i in ids]

    def add(self, doc_id: str, metadata: Dict) -> None:
        """Helper for tests -- not part of the abstract interface."""
        self._entries[doc_id] = dict(metadata)


class MemoryKVBackend(KVBackend):
    """In-memory key-value store."""

    def __init__(self):
        self._store: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def incr(self, key: str, delta: int = 1) -> int:
        current = self._store.get(key, 0)
        if not isinstance(current, int):
            current = 0
        self._store[key] = current + delta
        return self._store[key]
