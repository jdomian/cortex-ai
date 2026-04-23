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

The filesystem implementation uses `fcntl.flock` for atomic prune. All `Memory*Backend` implementations use `threading.Lock` -- safe for concurrent Lambda warm-container invocations.

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
- Memory backend returns first-k entries without real embedding (suitable for tests only -- `distance=0.0` is a stub)

#### `add(ids: List[str], documents: List[str], metadatas: List[Dict], embeddings: Optional[List[List[float]]] = None) -> None`

Insert memories into the store.

- `embeddings`: optional pre-computed embeddings; if `None`, the backend generates them

#### `delete(ids: List[str]) -> None`

Remove memories by ID. No-op for IDs that don't exist.

#### `upsert(ids: List[str], documents: List[str], metadatas: List[Dict], embeddings: Optional[List[List[float]]] = None) -> None`

Insert or replace memories. Existing IDs are replaced; new IDs are inserted.

#### `close() -> None`

Default no-op. Override in backends with persistent connections (clients, sessions).

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

---

## Writing a Custom Backend

Implement the appropriate ABC (`STMBackend`, `VectorBackend`, or `KVBackend`), then
register via entry_points or `register_backend()`.

### Option 1: Entry-points (recommended for published adapter packages)

In your adapter's `pyproject.toml`:

```toml
[project.entry-points."cortex.backends"]
"stm.dynamodb"       = "my_adapter:DynamoDBSTM"
"vector.opensearch"  = "my_adapter:OpenSearchVector"
"kv.dynamodb"        = "my_adapter:DynamoDBKV"
```

Entry-point values must be callables that accept a `cfg` dict and return a backend
instance. Entry-points are discovered lazily at first `get_backend()` call.

Failed entry-point loads log a warning to stderr -- one bad plugin does not crash cortex.

### Option 2: Direct registration (scripts, notebooks, one-off integrations)

```python
from cortex.backends import register_backend

def my_factory(cfg: dict):
    return MySTMBackend(table=cfg.get("table", "cortex-stm"))

register_backend("stm", "my_backend", my_factory)
```

Then set `type: my_backend` under `backends.stm` in `~/.cortex/config.yaml` (or
`CORTEX_CONFIG_PATH`).

### Minimum viable VectorBackend

```python
from cortex.backends.base import VectorBackend

class MyVectorBackend(VectorBackend):
    def get_all(self, filters=None, include=None): ...
    def update_metadata(self, ids, metadatas): ...
    def query_similar(self, text, k=10): ...
    def add(self, ids, documents, metadatas, embeddings=None): ...
    def delete(self, ids): ...
    def upsert(self, ids, documents, metadatas, embeddings=None): ...
```
