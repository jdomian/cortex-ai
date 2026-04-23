"""Filesystem reference implementations of Cortex storage backends.

FilesystemSTMBackend: wraps existing JSONL log/fetch/prune logic.
FilesystemVectorBackend: wraps local ChromaDB (lazy import).
FilesystemKVBackend: JSON file per key under ~/.cortex/kv/.

These are the defaults -- matching v0.5.0 behavior exactly.
ChromaDB is imported lazily inside methods to avoid Lambda cold-start penalty.
"""
import json
import os
import time
from typing import Any, Dict, List, Optional

from .base import KVBackend, STMBackend, VectorBackend


class FilesystemSTMBackend(STMBackend):
    """Default STM backend: JSONL file + fcntl lock for atomic prune."""

    def __init__(self, path: str = None):
        if path is None:
            path = os.path.expanduser("~/.cortex/stm/72h.jsonl")
        self.path = os.path.expanduser(path)
        self._base = os.path.dirname(self.path)
        self._lock_path = os.path.join(self._base, ".prune.lock")
        self._prune_ep_path = os.path.join(self._base, ".last-prune-epoch")
        self._drops_file = os.path.join(self._base, ".secret-filter-drops")

    def append(self, event: dict) -> bool:
        from cortex.stm.log import log as _log_fn
        os.makedirs(self._base, exist_ok=True)
        return _log_fn(event, self.path, drops_file=self._drops_file)

    def fetch(self, window_hours: int = 72, filters: Optional[Dict] = None) -> List[Dict]:
        from cortex.stm.fetch import fetch as _fetch_fn
        f = filters or {}
        return _fetch_fn(
            self.path,
            project=f.get("project"),
            day=f.get("day"),
            session=f.get("session"),
            intent=f.get("intent"),
            window_hours=window_hours,
        )

    def prune(self, older_than_hours: int = 72) -> Dict:
        from cortex.stm.prune import prune as _prune_fn
        os.makedirs(self._base, exist_ok=True)
        kept, dropped = _prune_fn(
            self.path, self._lock_path, self._prune_ep_path,
            older_than_hours=older_than_hours,
        )
        return {"kept": kept, "dropped": dropped}


class FilesystemVectorBackend(VectorBackend):
    """Vector backend backed by local ChromaDB.

    ChromaDB is imported lazily inside each method to avoid cold-start cost.
    """

    def __init__(self, palace_path: str = None, collection_name: str = None):
        self.palace_path = os.path.expanduser(
            palace_path or os.environ.get("CORTEX_PALACE_PATH", "~/.cortex/palace")
        )
        self.collection_name = collection_name or "memories"

    def _get_collection(self):
        import chromadb
        client = chromadb.PersistentClient(path=self.palace_path)
        return client.get_or_create_collection(self.collection_name)

    def get_all(self, filters: Optional[Dict] = None,
                include: Optional[List[str]] = None) -> Dict:
        try:
            col = self._get_collection()
            kwargs = {}
            if include:
                kwargs["include"] = include
            if filters:
                kwargs["where"] = filters
            return col.get(**kwargs)
        except Exception:
            return {"ids": [], "metadatas": []}

    def update_metadata(self, ids: List[str], metadatas: List[Dict]) -> None:
        if not ids:
            return
        col = self._get_collection()
        col.update(ids=ids, metadatas=metadatas)

    def query_similar(self, text: str, k: int = 10) -> List[Dict]:
        try:
            col = self._get_collection()
            results = col.query(query_texts=[text], n_results=k)
            out = []
            ids = (results.get("ids") or [[]])[0]
            metas = (results.get("metadatas") or [[]])[0]
            dists = (results.get("distances") or [[]])[0]
            for i, doc_id in enumerate(ids):
                out.append({
                    "id": doc_id,
                    "metadata": metas[i] if i < len(metas) else {},
                    "distance": dists[i] if i < len(dists) else None,
                })
            return out
        except Exception:
            return []


class FilesystemKVBackend(KVBackend):
    """Key-value backend: one JSON file per key under a directory."""

    def __init__(self, path: str = None):
        self._dir = os.path.expanduser(path or "~/.cortex/kv")

    def _key_path(self, key: str) -> str:
        safe = key.replace("/", "_").replace("..", "_")
        return os.path.join(self._dir, safe + ".json")

    def get(self, key: str) -> Optional[Any]:
        p = self._key_path(key)
        if not os.path.exists(p):
            return None
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        os.makedirs(self._dir, exist_ok=True)
        p = self._key_path(key)
        with open(p, "w") as f:
            json.dump(value, f)

    def incr(self, key: str, delta: int = 1) -> int:
        current = self.get(key)
        if not isinstance(current, int):
            current = 0
        new_val = current + delta
        self.set(key, new_val)
        return new_val
