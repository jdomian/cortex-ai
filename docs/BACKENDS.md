# Cortex Backend Interface Reference

Three abstract base classes define the storage contract for cortex-recall.
All are in `cortex.backends.base`.

---

## STMBackend

Append-only 72h event log. Powers `cortex.stm.STM`.

```python
from cortex.backends.base import STMBackend
```

### Methods

#### `append(event: dict) -> bool`

Append an event to the log.

- `event`: dict with at minimum `{"epoch": int, "project": str, "query_head": str}`
- Returns `True` if written, `False` if filtered (e.g., secret detected) or deduped
- Must be safe to call concurrently from multiple threads/processes

#### `fetch(window_hours: int = 72, filters: Optional[Dict] = None) -> List[Dict]`

Return events within the time window, optionally filtered.

- `window_hours`: only return events newer than `now - window_hours * 3600`
- `filters`: optional dict with keys `project`, `day` (YYYY-MM-DD), `session`, `intent`
- Returns list of event dicts, newest-first is recommended but not required

#### `prune(older_than_hours: int = 72) -> Dict`

Remove expired events.

- Returns `{"kept": int, "dropped": int}`
- Should be idempotent and atomic where possible

#### `close() -> None`

Flush buffers and disconnect. Default no-op for simple backends.

### Error semantics

- `append` should never raise -- return `False` on any error
- `fetch` should return `[]` on any error (log the error internally)
- `prune` should return `{"kept": 0, "dropped": 0}` on error
- `close` should swallow errors

### Thread safety

The filesystem implementation uses `fcntl.flock` for atomic prune. Memory implementation is not thread-safe (single-threaded use expected in tests/Lambda).

---

## VectorBackend

Semantic vector store. Powers `cortex.dream.Dream` maintenance steps (consolidate, decay).

```python
from cortex.backends.base import VectorBackend
```

### Methods

#### `get_all(filters: Optional[Dict] = None, include: Optional[List[str]] = None) -> Dict`

Return entries as a ChromaDB-shaped dict.

- `filters`: optional metadata filter (same format as ChromaDB `where=` clause)
- `include`: list of fields to include (e.g., `["metadatas", "documents"]`)
- Returns `{"ids": List[str], "metadatas": List[Dict], ...}`

#### `update_metadata(ids: List[str], metadatas: List[Dict]) -> None`

Batch-update metadata for given IDs.

- `ids` and `metadatas` must be the same length
- Should be a no-op for unknown IDs (or upsert, depending on backend)

#### `query_similar(text: str, k: int = 10) -> List[Dict]`

Return top-k most similar entries.

- Returns list of `{"id": str, "metadata": Dict, "distance": float}`
- Memory backend returns first-k entries without real embedding (suitable for tests only)

---

## KVBackend

Small key-value store for thresholds, feedback counters, last-prune epochs.

```python
from cortex.backends.base import KVBackend
```

### Methods

#### `get(key: str) -> Optional[Any]`

Return value for key, or `None` if absent.

#### `set(key: str, value: Any) -> None`

Set key to value. Overwrites existing value.

#### `incr(key: str, delta: int = 1) -> int`

Increment integer value by delta. Creates key with value `delta` if absent.

---

## Built-in Implementations

| Class | Category | Notes |
|-------|----------|-------|
| `FilesystemSTMBackend` | stm | JSONL + fcntl lock. Default. |
| `FilesystemVectorBackend` | vector | Local ChromaDB. Default. |
| `FilesystemKVBackend` | kv | One JSON file per key. Default. |
| `MemorySTMBackend` | stm | In-memory list. Tests + Lambda. |
| `MemoryVectorBackend` | vector | In-memory dict. No real embeddings. Tests only. |
| `MemoryKVBackend` | kv | In-memory dict. Tests + Lambda. |

All classes importable from `cortex.backends`:

```python
from cortex.backends import (
    FilesystemSTMBackend, FilesystemVectorBackend, FilesystemKVBackend,
    MemorySTMBackend, MemoryVectorBackend, MemoryKVBackend,
)
```

---

## Registry API

```python
from cortex.backends import get_backend, register_backend

# Resolve from config (returns instantiated backend)
stm = get_backend("stm")
stm = get_backend("stm", config_path="/path/to/config.yaml")

# Register a custom factory
register_backend("stm", "dynamodb", lambda cfg: MyDynamoSTM(cfg["table_name"]))
```

`get_backend` raises `ValueError` if the configured type is not registered.

External packages can also register via Python entry_points under group `cortex.backends`.
Entry point name format: `"<category>.<type_name>"`.
