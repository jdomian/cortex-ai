"""Integration tests for Dream with memory backends (Lambda smoke proof)."""
import time
import pytest

from cortex.backends.memory import MemorySTMBackend, MemoryVectorBackend, MemoryKVBackend
from cortex.dream import Dream


class TestDreamWithMemoryBackends:
    def test_dream_runs_with_memory_backends(self):
        """Lambda smoke proof: Dream runs end-to-end with no filesystem or ChromaDB."""
        dream = Dream(
            vector_backend=MemoryVectorBackend(),
            stm_backend=MemorySTMBackend(),
            kv_backend=MemoryKVBackend(),
        )
        result = dream.run()
        assert set(result.keys()) == {"prune_72h", "consolidate", "decay", "patterns"}
        for step_name, step_result in result.items():
            assert "error" not in step_result or step_result.get("error") is None, \
                f"Step {step_name} returned error: {step_result.get('error')}"

    def test_dream_default_no_backend_args_still_works(self):
        """Back-compat: Dream() with no args must not crash."""
        dream = Dream()
        # Just verify instantiation and step dispatch wiring is intact.
        # We don't call run() to avoid touching real ChromaDB/filesystem in tests.
        assert dream._vector is None
        assert dream._stm is None
        assert dream._kv is None

    def test_dream_partial_backends(self):
        """Only some backends specified -- unspecified ones use defaults."""
        dream = Dream(stm_backend=MemorySTMBackend())
        assert dream._stm is not None
        assert dream._vector is None  # not set, will default to filesystem in step
