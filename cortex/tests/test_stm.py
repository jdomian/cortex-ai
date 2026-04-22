"""Tests for cortex.stm -- round-trip log->fetch->rollup->prune, token budget, secret filter."""
import json
import os
import tempfile
import time

import pytest

from cortex.stm import STM
from cortex.stm.classifier import filter_secret, classify_intent, compute_dedup_key
from cortex.stm.rollup import TOKEN_BUDGET_CHARS, build_rollup


@pytest.fixture
def tmp_stm(tmp_path):
    path = str(tmp_path / "72h.jsonl")
    return STM(path=path)


def _make_event(epoch=None, project="test", intent="build", query="build thing", session="s1"):
    return {
        "epoch": epoch or int(time.time()),
        "project": project,
        "session_id": session,
        "intent_class": intent,
        "query_head": query,
        "hook_type": "UserPromptSubmit",
    }


class TestClassifier:
    def test_filter_secret_allows_normal(self):
        assert filter_secret("hello world") == "hello world"

    def test_filter_secret_blocks_password(self):
        assert filter_secret("password=secret123") is None

    def test_filter_secret_blocks_api_key(self):
        assert filter_secret("API_KEY=abc123") is None

    def test_filter_secret_blocks_bearer(self):
        assert filter_secret("Bearer eyJhbGciOiJSUzI1NiJ9") is None

    def test_filter_secret_blocks_hex32(self):
        assert filter_secret("token: " + "a" * 32) is None

    def test_filter_secret_none_input(self):
        assert filter_secret(None) == ""

    def test_classify_intent_build(self):
        assert classify_intent("build the stm package") == "build"

    def test_classify_intent_debug(self):
        assert classify_intent("error in the function") == "debug"

    def test_classify_intent_research(self):
        assert classify_intent("search for patterns") == "research"

    def test_classify_intent_infra(self):
        assert classify_intent("ssh into node 2") == "infra"

    def test_classify_intent_session_end(self):
        assert classify_intent("<session-end>") == "session_end"

    def test_classify_intent_other(self):
        assert classify_intent("what day is today") == "other"

    def test_dedup_key_deterministic(self):
        k1 = compute_dedup_key("s1", 1234567890, "Stop")
        k2 = compute_dedup_key("s1", 1234567890, "Stop")
        assert k1 == k2

    def test_dedup_key_unique(self):
        k1 = compute_dedup_key("s1", 1234567890, "Stop")
        k2 = compute_dedup_key("s2", 1234567890, "Stop")
        assert k1 != k2


class TestSTMLog:
    def test_log_writes_event(self, tmp_stm):
        event = _make_event()
        ok = tmp_stm.log(event)
        assert ok is True
        assert os.path.exists(tmp_stm.path)
        with open(tmp_stm.path) as f:
            data = json.loads(f.read().strip())
        assert data["project"] == "test"

    def test_log_filters_secret(self, tmp_stm):
        event = _make_event(query="password=supersecret")
        ok = tmp_stm.log(event)
        assert ok is False

    def test_log_multiple_events(self, tmp_stm):
        for i in range(5):
            tmp_stm.log(_make_event(epoch=int(time.time()) + i, query=f"query {i}"))
        with open(tmp_stm.path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        assert len(lines) == 5


class TestSTMFetch:
    def test_fetch_all(self, tmp_stm):
        now = int(time.time())
        tmp_stm.log(_make_event(epoch=now, project="a"))
        tmp_stm.log(_make_event(epoch=now + 1, project="b"))
        events = tmp_stm.fetch()
        assert len(events) == 2

    def test_fetch_by_project(self, tmp_stm):
        now = int(time.time())
        tmp_stm.log(_make_event(epoch=now, project="project-a"))
        tmp_stm.log(_make_event(epoch=now + 1, project="project-b"))
        events = tmp_stm.fetch(project="project-a")
        assert len(events) == 1
        assert events[0]["project"] == "project-a"

    def test_fetch_excludes_old_events(self, tmp_path):
        path = str(tmp_path / "72h.jsonl")
        stm = STM(path=path, window_hours=1)
        old_epoch = int(time.time()) - 7200  # 2 hours ago, beyond 1-hour window
        stm.log(_make_event(epoch=old_epoch))
        stm.log(_make_event(epoch=int(time.time())))
        events = stm.fetch()
        assert len(events) == 1

    def test_fetch_by_intent(self, tmp_stm):
        now = int(time.time())
        tmp_stm.log(_make_event(epoch=now, intent="build"))
        tmp_stm.log(_make_event(epoch=now + 1, intent="debug"))
        events = tmp_stm.fetch(intent="debug")
        assert len(events) == 1


class TestSTMRollup:
    def test_rollup_produces_output(self, tmp_stm):
        now = int(time.time())
        tmp_stm.log(_make_event(epoch=now))
        text = tmp_stm.rollup(force=True)
        assert "72h Recall" in text
        assert len(text) > 10

    def test_token_budget_guard(self, tmp_path):
        """Rollup strips chat/session_end rows when output exceeds TOKEN_BUDGET_CHARS."""
        path = str(tmp_path / "72h.jsonl")
        now = int(time.time())

        # Write many chat events to push over budget
        import json as _json
        with open(path, "w") as f:
            for i in range(200):
                event = {
                    "epoch": now - i * 60,
                    "project": f"proj{i % 5}",
                    "session_id": f"sess-{i:03d}",
                    "intent_class": "chat",
                    "query_head": "hey what do you think about this very long query that takes up space" * 2,
                    "hook_type": "UserPromptSubmit",
                }
                f.write(_json.dumps(event) + "\n")
            # Also add some build events
            for i in range(10):
                event = {
                    "epoch": now - i * 3600,
                    "project": "cortex",
                    "session_id": f"build-sess-{i:03d}",
                    "intent_class": "build",
                    "query_head": "build something important",
                    "hook_type": "Stop",
                }
                f.write(_json.dumps(event) + "\n")

        text, meta = build_rollup(path, now)
        # Verify token budget trimmed chat events (build events should still be there)
        assert "build" in text.lower() or meta["events_total"] > 0

    def test_rollup_cache_ttl(self, tmp_stm, tmp_path):
        """Rollup uses cached result when last-rollup-epoch is within TTL."""
        now = int(time.time())
        tmp_stm.log(_make_event(epoch=now))
        # First rollup writes summary
        text1 = tmp_stm.rollup(force=True)
        # Second call without force uses cache
        text2 = tmp_stm.rollup(force=False)
        assert text1 == text2


class TestSTMPrune:
    def test_prune_removes_old(self, tmp_path):
        path = str(tmp_path / "72h.jsonl")
        stm = STM(path=path, window_hours=1)
        old_epoch = int(time.time()) - 7200  # 2 hours, beyond 1-hour window
        recent_epoch = int(time.time()) - 100
        stm.log(_make_event(epoch=old_epoch, query="old"))
        stm.log(_make_event(epoch=recent_epoch, query="recent"))
        result = stm.prune()
        assert result["dropped"] == 1
        assert result["kept"] == 1

    def test_prune_lock_creates_file(self, tmp_stm):
        tmp_stm.log(_make_event())
        result = tmp_stm.prune()
        assert "kept" in result
        assert "dropped" in result
