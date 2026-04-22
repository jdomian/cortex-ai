"""Tests for cortex.dream -- orchestrator fires all sweeps, error isolation."""
import json
import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from cortex.dream import Dream, run_nightly


class TestDreamOrchestrator:
    def test_run_returns_all_steps(self):
        """Orchestrator returns results for all steps even if steps fail."""
        dream = Dream()
        with patch("cortex.dream.orchestrator.prune_72h") as mock_prune, \
             patch("cortex.dream.orchestrator.consolidate") as mock_cons, \
             patch("cortex.dream.orchestrator.decay") as mock_decay, \
             patch("cortex.dream.orchestrator._patterns_mod") as mock_pat:

            mock_prune.run.return_value = {"step": "prune_72h", "kept": 5, "dropped": 2}
            mock_cons.run.return_value = {"step": "consolidate", "unsaved": 1}
            mock_decay.run.return_value = {"step": "decay", "updated": 3}
            mock_pat.run.return_value = {"step": "patterns", "processed": 4}

            result = dream.run()

        assert "prune_72h" in result
        assert "consolidate" in result
        assert "decay" in result
        assert "patterns" in result

    def test_error_in_one_step_does_not_block_others(self):
        """If one step throws, orchestrator continues with remaining steps."""
        dream = Dream()
        with patch("cortex.dream.orchestrator.prune_72h") as mock_prune, \
             patch("cortex.dream.orchestrator.consolidate") as mock_cons, \
             patch("cortex.dream.orchestrator.decay") as mock_decay, \
             patch("cortex.dream.orchestrator._patterns_mod") as mock_pat:

            mock_prune.run.side_effect = RuntimeError("prune exploded")
            mock_cons.run.return_value = {"step": "consolidate", "unsaved": 0}
            mock_decay.run.return_value = {"step": "decay", "updated": 0}
            mock_pat.run.return_value = {"step": "patterns", "processed": 0}

            result = dream.run()

        assert "error" in result["prune_72h"]
        assert result["consolidate"]["step"] == "consolidate"
        assert result["decay"]["step"] == "decay"
        assert result["patterns"]["step"] == "patterns"

    def test_run_nightly_delegates_to_dream(self):
        with patch("cortex.dream.orchestrator.Dream") as MockDream:
            mock_instance = MagicMock()
            MockDream.return_value = mock_instance
            mock_instance.run.return_value = {"prune_72h": {}, "consolidate": {}}
            result = run_nightly()
        mock_instance.run.assert_called_once()


class TestDreamConsolidate:
    def test_consolidate_handles_missing_projects_dir(self):
        from cortex.dream import consolidate
        with patch("cortex.dream.consolidate.os.path.isdir", return_value=False):
            result = consolidate.run()
        assert result["step"] == "consolidate"
        assert result["orphaned"] == 0 or "message" in result


class TestDreamDecay:
    def test_decay_handles_missing_chromadb(self):
        from cortex.dream import decay
        import sys
        import types
        fake_chroma = types.ModuleType("chromadb")
        fake_chroma.PersistentClient = lambda path: (_ for _ in ()).throw(Exception("no db"))
        with patch.dict(sys.modules, {"chromadb": fake_chroma}):
            result = decay.run()
        assert result["step"] == "decay"
        assert "error" in result
