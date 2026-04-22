"""cortex.stm -- L2 Short-Term Memory (72h deterministic event log)."""
import os
from .classifier import filter_secret, classify_intent, compute_dedup_key
from .log import log as _log_fn
from .fetch import fetch as _fetch_fn, emit_markdown, emit_jsonl
from .rollup import rollup as _rollup_fn, build_rollup
from .prune import prune as _prune_fn

_DEFAULT_BASE = os.path.expanduser("~/.cortex/stm")


def _stm_path(base, filename):
    return os.path.join(base, filename)


class STM:
    def __init__(self, path=None, window_hours=72, rollup_cache_ttl=900):
        if path is None:
            path = os.path.join(_DEFAULT_BASE, "72h.jsonl")
        self.path = os.path.expanduser(path)
        self._base = os.path.dirname(self.path)
        self.window_hours = window_hours
        self.rollup_cache_ttl = rollup_cache_ttl

    @property
    def _summary_path(self):
        return os.path.join(self._base, "72h-summary.md")

    @property
    def _rollup_ep_path(self):
        return os.path.join(self._base, ".last-rollup-epoch")

    @property
    def _lock_path(self):
        return os.path.join(self._base, ".prune.lock")

    @property
    def _prune_ep_path(self):
        return os.path.join(self._base, ".last-prune-epoch")

    @property
    def _drops_file(self):
        return os.path.join(self._base, ".secret-filter-drops")

    def log(self, event: dict) -> bool:
        return _log_fn(event, self.path, drops_file=self._drops_file)

    def fetch(self, project=None, day=None, session=None, intent=None):
        return _fetch_fn(self.path, project=project, day=day, session=session,
                         intent=intent, window_hours=self.window_hours)

    def rollup(self, force=False):
        text, meta = _rollup_fn(self.path, self._summary_path, self._rollup_ep_path,
                                force=force, window_hours=self.window_hours)
        return text

    def prune(self):
        kept, dropped = _prune_fn(self.path, self._lock_path, self._prune_ep_path,
                                  older_than_hours=self.window_hours)
        return {"kept": kept, "dropped": dropped}


# Module-level convenience functions (use default ~/.cortex/stm/72h.jsonl)
def log(event: dict) -> bool:
    return STM().log(event)


def fetch(**filters):
    return STM().fetch(**filters)


def rollup(force=False) -> str:
    return STM().rollup(force=force)


def prune() -> dict:
    return STM().prune()


__all__ = [
    "STM", "log", "fetch", "rollup", "prune",
    "filter_secret", "classify_intent", "compute_dedup_key",
]
