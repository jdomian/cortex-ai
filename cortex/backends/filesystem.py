"""Filesystem reference implementations of Cortex storage backends.

FilesystemSTMBackend: wraps existing JSONL log/fetch/prune logic.
FilesystemVectorBackend: wraps local ChromaDB (lazy import).
FilesystemKVBackend: JSON file per key under ~/.cortex/kv/.

These are the defaults -- matching v0.5.0 behavior exactly.
ChromaDB is imported lazily inside methods to avoid Lambda cold-start penalty.
"""
import fcntl
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from .base import KVBackend, LockLease, STMBackend, VectorBackend

# Stamp embedded in ChromaDB collection metadata at create/open time.
# Increment whenever embedder dimension or schema changes in a breaking way.
_CORTEX_SCHEMA_VERSION = 1


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


class CollectionSchemaMismatch(Exception):
    """Raised when an existing collection's schema version or embedder fingerprint
    does not match the current configuration. Run the migration script to re-embed:
        python -m cortex.scripts.migrate_collection --source <collection> --help
    """


class FilesystemVectorBackend(VectorBackend):
    """Vector backend backed by local ChromaDB.

    ChromaDB is imported lazily inside each method to avoid cold-start cost.
    On first open of an existing collection, the schema version stamp and
    embedder fingerprint are validated. A CollectionSchemaMismatch is raised
    if the collection was created with an incompatible embedder.
    """

    def __init__(self, palace_path: str = None, collection_name: str = None,
                 embedder_model_id: str = None, embedder_dimension: int = None):
        self.palace_path = os.path.expanduser(
            palace_path or os.environ.get("CORTEX_PALACE_PATH", "~/.cortex/palace")
        )
        self.collection_name = collection_name or "memories"
        self._embedder_model_id = embedder_model_id or "all-MiniLM-L6-v2"
        self._embedder_dimension = embedder_dimension or 384

    def _schema_metadata(self) -> dict:
        return {
            "cortex_schema_version": _CORTEX_SCHEMA_VERSION,
            "embedder_model_id": self._embedder_model_id,
            "embedder_dimension": self._embedder_dimension,
        }

    def _get_collection(self):
        import chromadb  # noqa: PLC0415
        client = chromadb.PersistentClient(path=self.palace_path)
        try:
            col = client.get_collection(self.collection_name)
            # Validate schema on existing collection
            meta = col.metadata or {}
            stored_version = meta.get("cortex_schema_version")
            stored_model = meta.get("embedder_model_id")
            stored_dim = meta.get("embedder_dimension")
            if stored_version is not None:
                if (stored_model and stored_model != self._embedder_model_id) or \
                        (stored_dim and stored_dim != self._embedder_dimension):
                    raise CollectionSchemaMismatch(
                        f"Collection '{self.collection_name}' was created with "
                        f"embedder='{stored_model}' dim={stored_dim}, but current config "
                        f"uses embedder='{self._embedder_model_id}' dim={self._embedder_dimension}. "
                        "Run: python -m cortex.scripts.migrate_collection --help"
                    )
            return col
        except CollectionSchemaMismatch:
            raise
        except Exception:
            # Collection does not exist -- create with schema stamp
            return client.get_or_create_collection(
                self.collection_name,
                metadata=self._schema_metadata()
            )

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

    def add(self, ids: List[str], documents: List[str],
            metadatas: List[Dict], embeddings: Optional[List[List[float]]] = None) -> None:
        """Insert memories into ChromaDB."""
        import chromadb  # noqa: F401 -- lazy import preserved for Lambda cold-start
        col = self._get_collection()
        kwargs: Dict = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if embeddings is not None:
            kwargs["embeddings"] = embeddings
        col.add(**kwargs)

    def delete(self, ids: List[str]) -> None:
        """Remove memories by ID from ChromaDB."""
        import chromadb  # noqa: F401 -- lazy import preserved
        if not ids:
            return
        col = self._get_collection()
        col.delete(ids=ids)

    def upsert(self, ids: List[str], documents: List[str],
               metadatas: List[Dict], embeddings: Optional[List[List[float]]] = None) -> None:
        """Insert or replace memories in ChromaDB. Deduplicates by ID."""
        import chromadb  # noqa: F401 -- lazy import preserved
        col = self._get_collection()
        kwargs: Dict = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if embeddings is not None:
            kwargs["embeddings"] = embeddings
        col.upsert(**kwargs)


class FilesystemKVBackend(KVBackend):
    """Key-value backend: one JSON file per key under a directory.

    Locking uses fcntl advisory locks with a separate .lock file per key.
    The lease token is a UUID4 hex stored alongside the expiry epoch, so
    a crashed worker's lock will auto-expire even without an active release.
    """

    def __init__(self, path: str = None):
        self._dir = os.path.expanduser(path or "~/.cortex/kv")

    def _key_path(self, key: str) -> str:
        safe = key.replace("/", "_").replace("..", "_")
        return os.path.join(self._dir, safe + ".json")

    def _lock_path(self, key: str) -> str:
        safe = key.replace("/", "_").replace("..", "_")
        return os.path.join(self._dir, safe + ".lease.json")

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

    # ------------------------------------------------------------------
    # Locking
    # ------------------------------------------------------------------

    def supports_locking(self) -> bool:
        return True

    def acquire_lock(self, key: str, ttl_sec: int) -> Optional[LockLease]:
        """Try to acquire exclusive lock. Returns LockLease on success, None if held."""
        os.makedirs(self._dir, exist_ok=True)
        lp = self._lock_path(key)
        lf = open(lp, "a+")
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lf.close()
            return None

        try:
            lf.seek(0)
            raw = lf.read().strip()
            now = time.time()
            if raw:
                try:
                    lease_data = json.loads(raw)
                    expires = lease_data.get("expires_at", 0)
                    if expires > now:
                        # Still held by a non-expired lease
                        return None
                except Exception:
                    pass

            token = uuid.uuid4().hex
            expires_at = now + ttl_sec
            lease_data = {"token": token, "expires_at": expires_at}
            lf.seek(0)
            lf.truncate()
            lf.write(json.dumps(lease_data))
            lf.flush()
        finally:
            try:
                fcntl.flock(lf, fcntl.LOCK_UN)
            except Exception:
                pass
            lf.close()

        return LockLease(key=key, token=token, expires_at=expires_at, _backend=self)

    def renew_lock(self, key: str, token: str, ttl_sec: int) -> bool:
        """Renew lease if token matches and has not expired."""
        lp = self._lock_path(key)
        if not os.path.exists(lp):
            return False
        lf = open(lp, "r+")
        try:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                lf.seek(0)
                raw = lf.read().strip()
                if not raw:
                    return False
                lease_data = json.loads(raw)
                if lease_data.get("token") != token:
                    return False
                if lease_data.get("expires_at", 0) <= time.time():
                    return False
                lease_data["expires_at"] = time.time() + ttl_sec
                lf.seek(0)
                lf.truncate()
                lf.write(json.dumps(lease_data))
                lf.flush()
                return True
            except Exception:
                return False
        finally:
            try:
                fcntl.flock(lf, fcntl.LOCK_UN)
            except Exception:
                pass
            lf.close()

    def release_lock(self, key: str, token: str) -> bool:
        """Release lease if token matches. Returns True if released."""
        lp = self._lock_path(key)
        if not os.path.exists(lp):
            return False
        lf = open(lp, "r+")
        try:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                lf.seek(0)
                raw = lf.read().strip()
                if not raw:
                    return False
                lease_data = json.loads(raw)
                if lease_data.get("token") != token:
                    return False
                lf.seek(0)
                lf.truncate()
                lf.flush()
                return True
            except Exception:
                return False
        finally:
            try:
                fcntl.flock(lf, fcntl.LOCK_UN)
            except Exception:
                pass
            lf.close()
