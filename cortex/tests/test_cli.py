"""Tests for cortex CLI dispatch -- stm and dream subcommands."""
import argparse
import json
import sys
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest


class TestSTMCLI:
    def _make_args(self, stm_command, **kwargs):
        args = argparse.Namespace(stm_command=stm_command, **kwargs)
        return args

    def test_stm_fetch_dispatches(self):
        from cortex.stm_cli import cmd_stm
        args = self._make_args("fetch", project=None, day=None, session=None,
                               intent=None, full=False, json=False)
        with patch("cortex.stm_cli.STM") as MockSTM:
            mock_stm = MagicMock()
            MockSTM.return_value = mock_stm
            mock_stm.fetch.return_value = []
            cmd_stm(args)
        mock_stm.fetch.assert_called_once()

    def test_stm_rollup_dispatches(self):
        from cortex.stm_cli import cmd_stm
        args = self._make_args("rollup", force=False)
        with patch("cortex.stm_cli.STM") as MockSTM:
            mock_stm = MagicMock()
            MockSTM.return_value = mock_stm
            mock_stm.rollup.return_value = "# 72h Recall\n"
            cmd_stm(args)
        mock_stm.rollup.assert_called_once_with(force=False)

    def test_stm_prune_dispatches(self):
        from cortex.stm_cli import cmd_stm
        args = self._make_args("prune")
        with patch("cortex.stm_cli.STM") as MockSTM:
            mock_stm = MagicMock()
            MockSTM.return_value = mock_stm
            mock_stm.prune.return_value = {"kept": 5, "dropped": 2}
            result = cmd_stm(args)
        mock_stm.prune.assert_called_once()

    def test_stm_unknown_command_returns_error(self):
        from cortex.stm_cli import cmd_stm
        args = self._make_args("unknown-cmd")
        rc = cmd_stm(args)
        assert rc == 1


class TestDreamCLI:
    def _make_args(self, dream_command, **kwargs):
        return argparse.Namespace(dream_command=dream_command, **kwargs)

    def test_dream_run_dispatches(self):
        from cortex.dream_cli import cmd_dream
        args = self._make_args("run")
        with patch("cortex.dream_cli.Dream") as MockDream:
            mock_inst = MagicMock()
            MockDream.return_value = mock_inst
            mock_inst.run.return_value = {}
            cmd_dream(args)
        mock_inst.run.assert_called_once()

    def test_dream_threshold_dispatches(self):
        from cortex.dream_cli import cmd_dream
        args = self._make_args("threshold")
        with patch("cortex.dream_cli.threshold") as mock_thr:
            mock_thr.get_state.return_value = {"current_threshold": 0.7}
            cmd_dream(args)
        mock_thr.get_state.assert_called_once()

    def test_dream_unknown_returns_error(self):
        from cortex.dream_cli import cmd_dream
        args = self._make_args("nope")
        rc = cmd_dream(args)
        assert rc == 1


class TestSubparserRegistration:
    def test_stm_subparser_registers(self):
        import argparse
        from cortex.stm_cli import add_stm_subparser
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        p_stm = add_stm_subparser(sub)
        assert p_stm is not None

    def test_dream_subparser_registers(self):
        import argparse
        from cortex.dream_cli import add_dream_subparser
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        p_dream = add_dream_subparser(sub)
        assert p_dream is not None
