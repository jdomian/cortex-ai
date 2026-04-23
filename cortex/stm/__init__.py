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
    def __init__(self, path=None, window_hours=72, rollup_cache_ttl=900, backend=None):
        self.window_hours = window_hours
        self.rollup_cache_ttl = rollup_cache_ttl

        if backend is not None:
            # NEW: caller-supplied backend (filesystem, memory, or third-party).
            # Set self.path and self._base from the backend when available so
            # filesystem-aware properties (_summary_path etc.) work safely.
            # For memory/remote backends these will be None -- properties guard
            # against that by returning None rather than crashing.
            self._backend = backend
            self.path = getattr(backend, "path", None)
            self._base = os.path.dirname(self.path) if self.path else None
        else:
            # Legacy path: construct filesystem backend internally.
            # Matches v0.5.0 behavior exactly.
            if path is None:
                path = os.path.join(_DEFAULT_BASE, "72h.jsonl")
            self.path = os.path.expanduser(path)
            self._base = os.path.dirname(self.path)
            from cortex.backends.filesystem import FilesystemSTMBackend
            self._backend = FilesystemSTMBackend(path=self.path)

    @property
    def _summary_path(self):
        if self._base is None:
            return None
        return os.path.join(self._base, "72h-summary.md")

    @property
    def _rollup_ep_path(self):
        if self._base is None:
            return None
        return os.path.join(self._base, ".last-rollup-epoch")

    @property
    def _lock_path(self):
        if self._base is None:
            return None
        return os.path.join(self._base, ".prune.lock")

    @property
    def _prune_ep_path(self):
        if self._base is None:
            return None
        return os.path.join(self._base, ".last-prune-epoch")

    @property
    def _drops_file(self):
        if self._base is None:
            return None
        return os.path.join(self._base, ".secret-filter-drops")

    def log(self, event: dict) -> bool:
        return self._backend.append(event)

    def fetch(self, project=None, day=None, session=None, intent=None):
        filters = {}
        if project is not None:
            filters["project"] = project
        if day is not None:
            filters["day"] = day
        if session is not None:
            filters["session"] = session
        if intent is not None:
            filters["intent"] = intent
        return self._backend.fetch(window_hours=self.window_hours, filters=filters)

    def rollup(self, force=False):
        if self._base is None:
            # Non-filesystem backend: render text from events, skip file writes.
            events = self._backend.fetch(window_hours=self.window_hours, filters={})
            return emit_markdown(events, full=force)
        # Filesystem path: v0.5.0 behavior unchanged.
        text, meta = _rollup_fn(
            self.path, self._summary_path, self._rollup_ep_path,
            force=force, window_hours=self.window_hours,
        )
        return text

    def prune(self):
        # Delegate entirely to backend -- each backend handles its own
        # locking and epoch bookkeeping internally.
        return self._backend.prune(older_than_hours=self.window_hours)


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
