"""Tests for cortex.backends -- registry, filesystem, memory implementations,
and regression tests for Gemini-identified blockers (#1, #2, #3, Fix-in-Flight #4).
"""
import os
import sys
import time

import pytest

from cortex.backends import (
    FilesystemSTMBackend, FilesystemKVBackend,
    MemorySTMBackend, MemoryVectorBackend, MemoryKVBackend,
    get_backend, register_backend,
    STMBackend, VectorBackend, KVBackend,
)
from cortex.stm import STM


# ---------------------------------------------------------------------------
# Filesystem STM backend
# ---------------------------------------------------------------------------

class TestFilesystemSTMBackend:
    def test_append_fetch(self, tmp_path):
        backend = FilesystemSTMBackend(path=str(tmp_path / "stm.jsonl"))
        backend.append({"epoch": int(time.time()), "project": "test", "query_head": "hi"})
        events = backend.fetch(window_hours=72, filters={})
        assert len(events) == 1

    def test_append_returns_bool(self, tmp_path):
        backend = FilesystemSTMBackend(path=str(tmp_path / "stm.jsonl"))
        result = backend.append({"epoch": int(time.time()), "project": "p", "query_head": "x"})
        assert isinstance(result, bool)

    def test_fetch_respects_window(self, tmp_path):
        backend = FilesystemSTMBackend(path=str(tmp_path / "stm.jsonl"))
        old_epoch = int(time.time()) - 7300
        recent_epoch = int(time.time()) - 100
        backend.append({"epoch": old_epoch, "project": "p", "query_head": "old"})
        backend.append({"epoch": recent_epoch, "project": "p", "query_head": "new"})
        events = backend.fetch(window_hours=1, filters={})
        assert len(events) == 1
        assert events[0]["query_head"] == "new"

    def test_prune_removes_old(self, tmp_path):
        backend = FilesystemSTMBackend(path=str(tmp_path / "stm.jsonl"))
        old = int(time.time()) - 7300
        recent = int(time.time()) - 100
        backend.append({"epoch": old, "project": "p", "query_head": "old"})
        backend.append({"epoch": recent, "project": "p", "query_head": "new"})
        result = backend.prune(older_than_hours=1)
        assert result["dropped"] == 1
        assert result["kept"] == 1


# ---------------------------------------------------------------------------
# Memory STM backend
# ---------------------------------------------------------------------------

class TestMemorySTMBackend:
    def test_roundtrip(self):
        backend = MemorySTMBackend()
        backend.append({"epoch": int(time.time()), "project": "test", "query_head": "hi"})
        assert len(backend.fetch(window_hours=72, filters={})) == 1

    def test_path_is_none(self):
        backend = MemorySTMBackend()
        assert backend.path is None

    def test_filter_by_project(self):
        backend = MemorySTMBackend()
        now = int(time.time())
        backend.append({"epoch": now, "project": "a", "query_head": "x"})
        backend.append({"epoch": now, "project": "b", "query_head": "y"})
        events = backend.fetch(window_hours=72, filters={"project": "a"})
        assert len(events) == 1
        assert events[0]["project"] == "a"

    def test_prune(self):
        backend = MemorySTMBackend()
        old = int(time.time()) - 7300
        recent = int(time.time()) - 100
        backend.append({"epoch": old, "project": "p", "query_head": "old"})
        backend.append({"epoch": recent, "project": "p", "query_head": "new"})
        result = backend.prune(older_than_hours=1)
        assert result["dropped"] == 1
        assert result["kept"] == 1


# ---------------------------------------------------------------------------
# Memory KV backend
# ---------------------------------------------------------------------------

class TestMemoryKVBackend:
    def test_get_set(self):
        kv = MemoryKVBackend()
        kv.set("foo", 42)
        assert kv.get("foo") == 42

    def test_get_missing_returns_none(self):
        kv = MemoryKVBackend()
        assert kv.get("nonexistent") is None

    def test_incr(self):
        kv = MemoryKVBackend()
        assert kv.incr("counter") == 1
        assert kv.incr("counter") == 2
        assert kv.incr("counter", delta=5) == 7


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_resolves_filesystem_default_no_config(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")  # doesn't exist
        backend = get_backend("stm", config_path=cfg_path)
        assert isinstance(backend, FilesystemSTMBackend)

    def test_resolves_memory_from_config(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("backends:\n  stm:\n    type: memory\n")
        backend = get_backend("stm", config_path=str(cfg))
        assert isinstance(backend, MemorySTMBackend)

    def test_resolves_kv_from_config(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("backends:\n  kv:\n    type: memory\n")
        backend = get_backend("kv", config_path=str(cfg))
        assert isinstance(backend, MemoryKVBackend)

    def test_rejects_unknown_type(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("backends:\n  stm:\n    type: s3_parquet\n")
        with pytest.raises(ValueError, match="unknown backend"):
            get_backend("stm", config_path=str(cfg))

    def test_external_register_backend(self):
        class CustomSTM(STMBackend):
            def append(self, event): return True
            def fetch(self, window_hours=72, filters=None): return []
            def prune(self, older_than_hours=72): return {"kept": 0, "dropped": 0}

        register_backend("stm", "custom_test", lambda cfg: CustomSTM())
        # Verify it resolves
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("backends:\n  stm:\n    type: custom_test\n")
            cfg_path = f.name
        try:
            backend = get_backend("stm", config_path=cfg_path)
            assert isinstance(backend, CustomSTM)
        finally:
            os.unlink(cfg_path)


# ---------------------------------------------------------------------------
# Regression: STM with memory backend (Gemini Blockers #1 and #2)
# ---------------------------------------------------------------------------

class TestSTMWithMemoryBackend:
    def test_rollup_does_not_crash(self):
        """Blocker #2: STM(backend=MemorySTMBackend()).rollup() must not AttributeError."""
        stm = STM(backend=MemorySTMBackend())
        stm.log({"epoch": int(time.time()), "project": "test",
                 "query_head": "hello", "session_id": "s1"})
        text = stm.rollup()
        assert isinstance(text, str)

    def test_prune_does_not_crash(self):
        """Blocker #2: STM(backend=MemorySTMBackend()).prune() must not crash."""
        stm = STM(backend=MemorySTMBackend())
        result = stm.prune()
        assert "kept" in result
        assert "dropped" in result

    def test_path_properties_with_memory_backend(self):
        """Blocker #1: accessing _*_path properties with memory backend must not AttributeError."""
        stm = STM(backend=MemorySTMBackend())
        assert stm._base is None
        assert stm._summary_path is None
        assert stm._lock_path is None
        assert stm._prune_ep_path is None
        assert stm._drops_file is None

    def test_fetch_works_with_memory_backend(self):
        stm = STM(backend=MemorySTMBackend())
        now = int(time.time())
        stm.log({"epoch": now, "project": "proj_a", "query_head": "test",
                 "session_id": "s1", "intent_class": "build"})
        stm.log({"epoch": now, "project": "proj_b", "query_head": "other",
                 "session_id": "s2", "intent_class": "debug"})
        all_events = stm.fetch()
        assert len(all_events) == 2
        a_events = stm.fetch(project="proj_a")
        assert len(a_events) == 1


# ---------------------------------------------------------------------------
# Regression: Dream step back-compat kwargs (Fix-in-Flight #4)
# ---------------------------------------------------------------------------

class TestDreamStepBackcompat:
    def test_consolidate_preserves_v050_kwargs(self, tmp_path):
        """Fix-in-Flight #4: consolidate.run(palace_path=...) must still work."""
        from cortex.dream import consolidate
        result = consolidate.run(palace_path=str(tmp_path), idle_threshold_hours=1)
        assert "step" in result
        assert result["step"] == "consolidate"

    def test_decay_preserves_v050_kwargs(self, tmp_path):
        """Fix-in-Flight #4: decay.run(palace_path=...) must still work."""
        from cortex.dream import decay
        result = decay.run(palace_path=str(tmp_path), collection_name="test")
        assert "step" in result
        assert result["step"] == "decay"

    def test_patterns_preserves_v050_kwargs(self, tmp_path):
        """Fix-in-Flight #4: patterns.run(events_path=..., db_path=...) must still work."""
        from cortex.dream import patterns as _patterns
        result = _patterns.run(
            events_path=str(tmp_path / "events.jsonl"),
            db_path=str(tmp_path / "patterns.db"),
        )
        assert "promoted" in result


# ---------------------------------------------------------------------------
# Regression: lazy ChromaDB import (Blocker #3)
# ---------------------------------------------------------------------------

class TestLazyChromaDBImport:
    def test_no_chromadb_import_at_module_level(self):
        """Blocker #3: importing backends/dream must not pull chromadb at module level."""
        before = "chromadb" in sys.modules

        import importlib
        import cortex.backends
        import cortex.backends.filesystem
        import cortex.dream.orchestrator

        after = "chromadb" in sys.modules

        # Only assert lazy-loading if chromadb was NOT already loaded
        if not before:
            assert not after, (
                "ChromaDB was loaded at import time. This breaks Lambda cold-start. "
                "Ensure all chromadb imports are inside function bodies."
            )
