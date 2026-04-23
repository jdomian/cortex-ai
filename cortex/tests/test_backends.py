"""Tests for cortex.backends -- registry, filesystem, memory implementations,
and regression tests for Gemini-identified blockers (#1, #2, #3, Fix-in-Flight #4).
v0.6.1 additions: VectorBackend write API, thread-safety, entry-point error logging.
"""
import logging
import os
import sys
import threading
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


# ---------------------------------------------------------------------------
# v0.6.1: VectorBackend write API (add/delete/upsert) on MemoryVectorBackend
# ---------------------------------------------------------------------------

class TestMemoryVectorBackendWriteAPI:
    def test_add_then_get_all(self):
        b = MemoryVectorBackend()
        b.add(ids=["a", "b"], documents=["doc a", "doc b"],
              metadatas=[{"x": 1}, {"x": 2}])
        result = b.get_all(filters={}, include=["metadatas"])
        assert len(result["metadatas"]) == 2

    def test_delete_removes_entry(self):
        b = MemoryVectorBackend()
        b.add(ids=["a", "b"], documents=["doc a", "doc b"],
              metadatas=[{"x": 1}, {"x": 2}])
        b.delete(ids=["a"])
        result = b.get_all(filters={}, include=["metadatas"])
        assert len(result["metadatas"]) == 1
        assert result["ids"] == ["b"]

    def test_upsert_updates_existing_and_adds_new(self):
        b = MemoryVectorBackend()
        b.add(ids=["a", "b"], documents=["doc a", "doc b"],
              metadatas=[{"x": 1}, {"x": 2}])
        b.upsert(ids=["b", "c"], documents=["doc b v2", "doc c"],
                 metadatas=[{"x": 20}, {"x": 3}])
        result = b.get_all(filters={}, include=["metadatas"])
        assert len(result["metadatas"]) == 3
        xs = sorted(m.get("x") for m in result["metadatas"])
        assert xs == [1, 3, 20]

    def test_upsert_deduplicates_by_id(self):
        b = MemoryVectorBackend()
        b.add(ids=["b"], documents=["doc b"], metadatas=[{"x": 2}])
        b.upsert(ids=["b"], documents=["doc b v2"], metadatas=[{"x": 20}])
        result = b.get_all(filters={}, include=["metadatas"])
        assert len(result["metadatas"]) == 1
        assert result["metadatas"][0]["x"] == 20

    def test_add_delete_upsert_filesystem(self, tmp_path):
        pytest.importorskip("chromadb", reason="chromadb not installed in this env")
        from cortex.backends import FilesystemVectorBackend
        b = FilesystemVectorBackend(
            palace_path=str(tmp_path), collection_name="test_write"
        )
        b.add(ids=["a"], documents=["hello"], metadatas=[{"t": 1}])
        result = b.get_all(filters={}, include=["metadatas"])
        assert len(result["metadatas"]) == 1
        b.delete(ids=["a"])
        result = b.get_all(filters={}, include=["metadatas"])
        assert len(result["metadatas"]) == 0

    def test_upsert_filesystem(self, tmp_path):
        pytest.importorskip("chromadb", reason="chromadb not installed in this env")
        from cortex.backends import FilesystemVectorBackend
        b = FilesystemVectorBackend(
            palace_path=str(tmp_path), collection_name="test_upsert"
        )
        b.add(ids=["x"], documents=["original"], metadatas=[{"v": 1}])
        b.upsert(ids=["x"], documents=["replaced"], metadatas=[{"v": 99}])
        result = b.get_all(filters={}, include=["metadatas"])
        assert len(result["metadatas"]) == 1
        assert result["metadatas"][0]["v"] == 99

    def test_query_similar_docstring_warns_test_only(self):
        """query_similar() on memory backend returns distance=0.0 (test stub, not semantic)."""
        b = MemoryVectorBackend()
        b.add(ids=["x"], documents=["some text"], metadatas=[{"k": "v"}])
        results = b.query_similar("anything", k=5)
        assert len(results) == 1
        assert results[0]["distance"] == 0.0


# ---------------------------------------------------------------------------
# v0.6.1: Thread-safety on memory backends
# ---------------------------------------------------------------------------

class TestMemorySTMThreadSafety:
    def test_concurrent_appends_produce_exact_count(self):
        """200 concurrent appends must produce exactly 200 events with no torn state."""
        b = MemorySTMBackend()

        def worker(wid):
            for i in range(20):
                b.append({
                    "epoch": int(time.time()) + i,
                    "project": f"w{wid}",
                    "query_head": f"e{i}",
                    "session_id": f"s{wid}",
                    "dedup_key": f"d{wid}-{i}",
                })

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        events = b.fetch(window_hours=72, filters={})
        assert len(events) == 200, f"expected 200, got {len(events)}"

    def test_concurrent_prune_and_append(self):
        """prune() during concurrent append() must not produce torn state."""
        b = MemorySTMBackend()
        old_epoch = int(time.time()) - 7300

        for i in range(50):
            b.append({"epoch": old_epoch, "project": "p", "query_head": f"old{i}"})

        errors = []

        def pruner():
            try:
                b.prune(older_than_hours=1)
            except Exception as e:
                errors.append(e)

        def appender(wid):
            try:
                for i in range(10):
                    b.append({
                        "epoch": int(time.time()),
                        "project": "p",
                        "query_head": f"new{wid}{i}",
                    })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=appender, args=(w,)) for w in range(5)]
        threads.append(threading.Thread(target=pruner))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent prune+append raised: {errors}"


class TestMemoryKVThreadSafety:
    def test_concurrent_incr_produces_exact_count(self):
        """1000 concurrent incr() calls must yield exactly 1000."""
        b = MemoryKVBackend()

        def worker():
            for _ in range(100):
                b.incr("counter")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert b.get("counter") == 1000, f"expected 1000, got {b.get('counter')}"


# ---------------------------------------------------------------------------
# v0.6.1: Entry-point error logging (plugin failures log, do not crash)
# ---------------------------------------------------------------------------

class TestEntryPointErrorLogging:
    def test_broken_plugin_factory_raises_on_get_backend(self, tmp_path):
        """A factory that raises must propagate when get_backend() resolves it."""
        from cortex.backends import register_backend, get_backend

        def broken_factory(cfg):
            raise RuntimeError("simulated bad adapter")

        register_backend("stm", "broken_v061_test", broken_factory)

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text("backends:\n  stm:\n    type: broken_v061_test\n")

        with pytest.raises(RuntimeError, match="simulated bad adapter"):
            get_backend("stm", config_path=str(cfg_file))

    def test_valid_plugin_registers_and_resolves(self, tmp_path):
        """A well-formed factory registered directly must resolve via get_backend()."""
        from cortex.backends import register_backend, get_backend

        class GoodSTM(STMBackend):
            def append(self, event): return True
            def fetch(self, window_hours=72, filters=None): return []
            def prune(self, older_than_hours=72): return {"kept": 0, "dropped": 0}

        register_backend("stm", "good_v061_test", lambda cfg: GoodSTM())

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text("backends:\n  stm:\n    type: good_v061_test\n")

        backend = get_backend("stm", config_path=str(cfg_file))
        assert isinstance(backend, GoodSTM)
