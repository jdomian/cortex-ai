"""Tests for cortex.dream.patterns -- event capture, clustering, promotion, rule generation."""
import json
import os
import tempfile
import time
from unittest.mock import patch, MagicMock

import pytest

from cortex.dream.patterns import (
    log_correction, promote_ready_patterns, merge_patterns, split_pattern, retire_pattern
)
from cortex.dream.patterns_db import all_patterns, put_pattern, get_pattern


@pytest.fixture
def tmp_events(tmp_path):
    return str(tmp_path / "correction-events.jsonl")


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "patterns.jsonl")


@pytest.fixture
def tmp_feedback(tmp_path):
    return str(tmp_path / "l1-feedback")


def _sample_correction(n=1, user_said="don't use Django"):
    return {
        "session_id": f"sess-{n:03d}",
        "user_said": user_said,
        "was_doing": "scaffolding web service",
        "context": "framework choice",
        "severity": "medium",
    }


class TestLogCorrection:
    def test_log_writes_event(self, tmp_events):
        eid = log_correction(_sample_correction(), events_path=tmp_events)
        assert eid is not None
        assert os.path.exists(tmp_events)
        with open(tmp_events) as f:
            data = json.loads(f.read().strip())
        assert data["user_said"] == "don't use Django"

    def test_dedup_within_window(self, tmp_events):
        corr = _sample_correction()
        eid1 = log_correction(corr, events_path=tmp_events)
        eid2 = log_correction(corr, events_path=tmp_events)  # same session + said_hash
        assert eid1 is not None
        assert eid2 is None  # dedup-skipped

    def test_different_session_not_deduped(self, tmp_events):
        eid1 = log_correction(_sample_correction(n=1), events_path=tmp_events)
        eid2 = log_correction(_sample_correction(n=2), events_path=tmp_events)
        assert eid1 is not None
        assert eid2 is not None


class TestPromote:
    def test_promotes_when_count_reaches_threshold(self, tmp_db, tmp_feedback):
        index_path = os.path.join(tmp_feedback, "INDEX.md")
        pattern = {
            "pattern_id": "test-django-pattern",
            "trigger_phrases": ["django", "framework"],
            "occurrence_count": 3,
            "first_seen_epoch": int(time.time()) - 1000,
            "last_seen_epoch": int(time.time()),
            "cluster_centroid": [0.1] * 10,
            "example_events": ["corr_001"],
            "promoted": False,
            "promoted_at_epoch": None,
            "promoted_rule_path": None,
            "retired": False,
            "stale": False,
        }
        put_pattern(pattern, tmp_db)
        promoted = promote_ready_patterns(promotion_threshold=3, db_path=tmp_db,
                                          feedback_dir=tmp_feedback, index_path=index_path)
        assert promoted == 1

        p = get_pattern("test-django-pattern", tmp_db)
        assert p["promoted"] is True
        assert p["promoted_rule_path"] is not None
        assert os.path.exists(p["promoted_rule_path"])

    def test_does_not_promote_below_threshold(self, tmp_db, tmp_feedback):
        index_path = os.path.join(tmp_feedback, "INDEX.md")
        pattern = {
            "pattern_id": "test-low-count",
            "trigger_phrases": ["something"],
            "occurrence_count": 2,
            "first_seen_epoch": int(time.time()),
            "last_seen_epoch": int(time.time()),
            "cluster_centroid": [0.1] * 10,
            "example_events": [],
            "promoted": False,
            "promoted_at_epoch": None,
            "promoted_rule_path": None,
            "retired": False,
            "stale": False,
        }
        put_pattern(pattern, tmp_db)
        promoted = promote_ready_patterns(promotion_threshold=3, db_path=tmp_db,
                                          feedback_dir=tmp_feedback, index_path=index_path)
        assert promoted == 0

    def test_does_not_repromote_already_promoted(self, tmp_db, tmp_feedback):
        index_path = os.path.join(tmp_feedback, "INDEX.md")
        pattern = {
            "pattern_id": "already-promoted",
            "trigger_phrases": ["x"],
            "occurrence_count": 5,
            "first_seen_epoch": int(time.time()),
            "last_seen_epoch": int(time.time()),
            "cluster_centroid": [0.1] * 10,
            "example_events": [],
            "promoted": True,  # already promoted
            "promoted_at_epoch": int(time.time()) - 100,
            "promoted_rule_path": "/some/path.md",
            "retired": False,
            "stale": False,
        }
        put_pattern(pattern, tmp_db)
        promoted = promote_ready_patterns(promotion_threshold=3, db_path=tmp_db,
                                          feedback_dir=tmp_feedback, index_path=index_path)
        assert promoted == 0


class TestMergeSplitRetire:
    def _make_pattern(self, pid, count=3, centroid=None):
        return {
            "pattern_id": pid,
            "trigger_phrases": ["word"],
            "occurrence_count": count,
            "first_seen_epoch": int(time.time()),
            "last_seen_epoch": int(time.time()),
            "cluster_centroid": centroid or [0.5] * 10,
            "example_events": ["e1"],
            "promoted": False,
            "promoted_at_epoch": None,
            "promoted_rule_path": None,
            "retired": False,
            "stale": False,
        }

    def test_merge_combines_two_patterns(self, tmp_db):
        p1 = self._make_pattern("p1", count=3, centroid=[0.5] * 10)
        p2 = self._make_pattern("p2", count=2, centroid=[0.6] * 10)
        put_pattern(p1, tmp_db)
        put_pattern(p2, tmp_db)
        result = merge_patterns("p1", "p2", db_path=tmp_db)
        assert result["merged"] is True
        merged = get_pattern("p1", tmp_db)
        assert merged["occurrence_count"] == 5  # 3 + 2
        assert get_pattern("p2", tmp_db) is None  # deleted

    def test_split_retires_pattern(self, tmp_db):
        p = self._make_pattern("split-me")
        put_pattern(p, tmp_db)
        result = split_pattern("split-me", db_path=tmp_db)
        assert result["split"] is True
        updated = get_pattern("split-me", tmp_db)
        assert updated["retired"] is True

    def test_retire_marks_pattern(self, tmp_db):
        p = self._make_pattern("retire-me")
        put_pattern(p, tmp_db)
        result = retire_pattern("retire-me", db_path=tmp_db)
        assert result["retired"] is True
        updated = get_pattern("retire-me", tmp_db)
        assert updated["retired"] is True

    def test_merge_missing_pattern_returns_error(self, tmp_db):
        p = self._make_pattern("exists")
        put_pattern(p, tmp_db)
        result = merge_patterns("exists", "does-not-exist", db_path=tmp_db)
        assert "error" in result
