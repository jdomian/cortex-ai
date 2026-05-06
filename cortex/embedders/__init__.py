"""cortex.embedders -- pluggable text embedding registry.

Built-in types:
  sentence_transformers  -- all-MiniLM-L6-v2, 384-dim (default)

External packages (e.g. cortex-backend-aws) register additional types via
Python entry_points group "cortex.embedders" or by calling register_embedder()
directly at import time.

Entry-point format (in your adapter package's pyproject.toml):

    [project.entry-points."cortex.embedders"]
    "bedrock" = "cortex_backend_aws.embedder_bedrock:factory"

Entry-point name format: "<name>" (single axis, no category prefix).
Value: a callable that accepts a cfg dict and returns an Embedder instance.

Usage:
    from cortex.embedders import get_embedder
    embedder = get_embedder()                   # default sentence_transformers
    embedder = get_embedder(config_path=None)   # reads config.yaml embedder block
"""
import logging
from typing import Callable, Dict, Optional

from .base import Embedder

_log = logging.getLogger("cortex.embedders")

_REGISTRY: Dict[str, Callable] = {}
_REGISTRY_POPULATED = False


def _populate_registry() -> None:
    global _REGISTRY_POPULATED
    if _REGISTRY_POPULATED:
        return
    from .sentence_transformers import factory as _st_factory
    _REGISTRY["sentence_transformers"] = _st_factory

    try:
        import importlib.metadata as ilm
        eps = ilm.entry_points(group="cortex.embedders")
    except Exception as e:
        _log.warning("cortex.embedders entry_points() call failed: %s", e)
        eps = []

    for ep in eps:
        try:
            factory = ep.load()
            _REGISTRY[ep.name] = factory
        except Exception as e:
            _log.warning(
                "cortex.embedders failed to load entry point %r: %s -- "
                "check that the adapter package is installed",
                ep.name, e,
            )

    _REGISTRY_POPULATED = True


def register_embedder(name: str, factory: Callable) -> None:
    """Register an embedder factory for external packages.

    Args:
        name: type string used in config.yaml embedder.type field
        factory: callable(cfg_dict) -> Embedder instance
    """
    _populate_registry()
    _REGISTRY[name] = factory


def get_embedder(
    config_path: Optional[str] = None,
    type_name: Optional[str] = None,
    extra_cfg: Optional[Dict] = None,
) -> Embedder:
    """Resolve and instantiate an embedder.

    Resolution order:
      1. Explicit type_name arg (highest priority -- CLI / test use)
      2. config.yaml embedder.type field
      3. sentence_transformers default (all-MiniLM-L6-v2, 384-dim)

    Falls back to sentence_transformers when no explicit type and no
    embedder block is present in config.

    Args:
        config_path: path to config.yaml; None uses CORTEX_CONFIG_PATH env var
                     then ~/.cortex/config.yaml then built-in defaults.
        type_name: explicit embedder type override (bypasses config.yaml).
                   Useful for CLI scripts like migrate_collection.py.
        extra_cfg: additional config dict merged into the embedder cfg
                   (only applies with explicit type_name).
    """
    _populate_registry()

    resolved_type = "sentence_transformers"
    cfg: Dict = {}

    if type_name:
        resolved_type = type_name
        cfg = dict(extra_cfg) if extra_cfg else {}
    else:
        try:
            from cortex.config import load_config
            full_cfg = load_config(config_path)
            embedder_cfg = full_cfg.get("embedder", {})
            resolved_type = embedder_cfg.get("type", "sentence_transformers")
            cfg = embedder_cfg
        except Exception as e:
            _log.debug("cortex.embedders: config load skipped: %s", e)

    if resolved_type not in _REGISTRY:
        available = list(_REGISTRY.keys())
        raise ValueError(
            f"unknown embedder type '{resolved_type}'. "
            f"Available: {available}. Register via register_embedder() or entry_points."
        )
    return _REGISTRY[resolved_type](cfg)


__all__ = ["Embedder", "get_embedder", "register_embedder"]
