"""cortex.backends -- pluggable storage backend registry.

Three categories:
  stm    -- append-only 72h event log (STMBackend)
  vector -- semantic vector store (VectorBackend)
  kv     -- key/value counters and thresholds (KVBackend)

Built-in types:
  stm:    filesystem (default), memory
  vector: chromadb_local (default), memory
  kv:     filesystem (default), memory

External packages (e.g. cortex-backend-dynamodb) register additional types
via Python entry_points group "cortex.backends" or by calling register_backend()
directly at import time.

Entry-point format (in your adapter package's pyproject.toml):

    [project.entry-points."cortex.backends"]
    "stm.dynamodb"       = "my_adapter:DynamoDBSTM"
    "vector.opensearch"  = "my_adapter:OpenSearchVector"
    "kv.dynamodb"        = "my_adapter:DynamoDBKV"

Entry-point name format: "<category>.<name>" (e.g. "stm.dynamodb").
Categories: "stm", "vector", "kv".
Value: a callable that accepts **cfg kwargs and returns a backend instance.

register_backend() vs entry_points:
  - register_backend() runs at import time (immediate, explicit)
  - entry_points are discovered lazily at first get_backend() call (automatic)
  Both are valid; prefer entry_points for published adapter packages.

Usage:
    from cortex.backends import get_backend, register_backend
    stm = get_backend("stm")              # filesystem default
    stm = get_backend("stm", config_path="/path/to/config.yaml")
"""
import logging
from typing import Callable, Dict, Tuple

from .base import KVBackend, STMBackend, VectorBackend

_log = logging.getLogger("cortex.backends")

# Registry is keyed by (category, type_name) -> factory(cfg_dict) -> backend instance.
# Populated lazily to avoid importing filesystem/memory modules at package import time,
# which would pull in chromadb transitively.
_REGISTRY: Dict[Tuple[str, str], Callable] = {}
_REGISTRY_POPULATED = False


def _populate_registry() -> None:
    global _REGISTRY_POPULATED
    if _REGISTRY_POPULATED:
        return
    from .filesystem import FilesystemSTMBackend, FilesystemVectorBackend, FilesystemKVBackend
    from .memory import MemorySTMBackend, MemoryVectorBackend, MemoryKVBackend

    _REGISTRY[("stm", "filesystem")] = lambda cfg: FilesystemSTMBackend(
        path=cfg.get("path")
    )
    _REGISTRY[("stm", "memory")] = lambda cfg: MemorySTMBackend()

    _REGISTRY[("vector", "chromadb_local")] = lambda cfg: FilesystemVectorBackend(
        palace_path=cfg.get("path"),
        collection_name=cfg.get("collection"),
    )
    _REGISTRY[("vector", "memory")] = lambda cfg: MemoryVectorBackend()

    _REGISTRY[("kv", "filesystem")] = lambda cfg: FilesystemKVBackend(
        path=cfg.get("path")
    )
    _REGISTRY[("kv", "memory")] = lambda cfg: MemoryKVBackend()

    # Discover entry_points plugins -- log failures, never swallow silently
    try:
        import importlib.metadata as ilm
        eps = ilm.entry_points(group="cortex.backends")
    except Exception as e:
        _log.warning("cortex.backends entry_points() call failed: %s", e)
        eps = []

    for ep in eps:
        try:
            factory = ep.load()
            parts = ep.name.split(".", 1)
            if len(parts) != 2:
                _log.warning(
                    "cortex.backends entry point %r has no category prefix "
                    "(expected '<category>.<name>' e.g. 'stm.dynamodb'); skipping",
                    ep.name,
                )
                continue
            _REGISTRY[(parts[0], parts[1])] = factory
        except Exception as e:
            _log.warning(
                "cortex.backends failed to load entry point %r: %s -- "
                "check that the adapter package is installed and its entry point "
                "declaration is correct",
                ep.name, e,
            )

    _REGISTRY_POPULATED = True


def register_backend(category: str, name: str, factory: Callable) -> None:
    """Register a backend factory for external packages.

    Args:
        category: "stm", "vector", or "kv"
        name: type string used in config.yaml (e.g. "dynamodb")
        factory: callable(cfg_dict) -> backend instance
    """
    _populate_registry()
    _REGISTRY[(category, name)] = factory


def get_backend(category: str, config_path: str = None):
    """Resolve and instantiate a backend from config.

    Falls back to filesystem defaults if config is absent or incomplete.

    Args:
        category: "stm", "vector", or "kv"
        config_path: path to config.yaml; None uses CORTEX_CONFIG_PATH env var
                     then ~/.cortex/config.yaml then built-in defaults

    Returns:
        Instantiated backend conforming to the appropriate abstract base class.

    Raises:
        ValueError: if the configured type name is not registered.
    """
    _populate_registry()

    from cortex.config import get_backend_config
    cfg = get_backend_config(category, config_path=config_path)
    type_name = cfg.get("type", _default_type(category))

    key = (category, type_name)
    if key not in _REGISTRY:
        available = [t for (c, t) in _REGISTRY if c == category]
        raise ValueError(
            f"unknown backend type '{type_name}' for category '{category}'. "
            f"Available: {available}. Register via register_backend() or entry_points."
        )
    return _REGISTRY[key](cfg)


def _default_type(category: str) -> str:
    defaults = {"stm": "filesystem", "vector": "chromadb_local", "kv": "filesystem"}
    return defaults.get(category, "filesystem")


__all__ = [
    "STMBackend", "VectorBackend", "KVBackend",
    "get_backend", "register_backend",
    # Concrete classes exposed for isinstance checks
    "FilesystemSTMBackend", "FilesystemVectorBackend", "FilesystemKVBackend",
    "MemorySTMBackend", "MemoryVectorBackend", "MemoryKVBackend",
]


def __getattr__(name):
    """Lazy import concrete classes on demand."""
    _filesystem = {
        "FilesystemSTMBackend", "FilesystemVectorBackend", "FilesystemKVBackend"
    }
    _memory = {
        "MemorySTMBackend", "MemoryVectorBackend", "MemoryKVBackend"
    }
    if name in _filesystem:
        from . import filesystem as _fs
        return getattr(_fs, name)
    if name in _memory:
        from . import memory as _mem
        return getattr(_mem, name)
    raise AttributeError(f"module 'cortex.backends' has no attribute '{name}'")
