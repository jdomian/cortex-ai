"""Adaptive similarity threshold manager for L5 pattern detection.

State persisted at ~/.cortex/l5/threshold.json with full history.
Config loaded from ~/.cortex/config.yaml (evolution section).
"""
import json
import os
import time
from typing import Dict, Any

_DEFAULT_CONFIG = {
    "initial_threshold": 0.7,
    "adaptive": True,
    "adapt_step": 0.02,
    "bootstrap_days": 30,
    "min_feedback_for_adapt": 5,
    "threshold_bounds": [0.55, 0.90],
}


def _load_config() -> Dict:
    config_path = os.path.expanduser("~/.cortex/config.yaml")
    if not os.path.exists(config_path):
        return _DEFAULT_CONFIG
    try:
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return {**_DEFAULT_CONFIG, **data.get("evolution", {})}
    except Exception:
        return _DEFAULT_CONFIG


def _state_path() -> str:
    return os.path.expanduser("~/.cortex/l5/threshold.json")


def _load_state() -> Dict:
    path = _state_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: Dict):
    path = _state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def get() -> float:
    """Return current effective threshold, respecting bootstrap freeze and bounds."""
    cfg = _load_config()
    state = _load_state()
    initial = cfg["initial_threshold"]
    bounds = cfg["threshold_bounds"]

    if not cfg.get("adaptive", True):
        return initial

    # Bootstrap period check
    install_epoch = state.get("install_epoch")
    if install_epoch is None:
        # First call -- record install time
        state["install_epoch"] = int(time.time())
        state["current_threshold"] = initial
        state["history"] = []
        state["feedback_count"] = 0
        _save_state(state)
        return initial

    bootstrap_seconds = cfg["bootstrap_days"] * 86400
    in_bootstrap = (int(time.time()) - install_epoch) < bootstrap_seconds
    feedback_count = state.get("feedback_count", 0)
    min_feedback = cfg.get("min_feedback_for_adapt", 5)

    if in_bootstrap or feedback_count < min_feedback:
        return initial

    current = state.get("current_threshold", initial)
    return max(bounds[0], min(bounds[1], current))


def record_merge_feedback(similarity: float):
    """Signal A: user says two patterns should have merged. Nudge threshold DOWN."""
    _adjust(-1, similarity, "merge_feedback")


def record_split_feedback(similarity: float):
    """Signal B: user says a pattern is incoherent (should have split). Nudge UP."""
    _adjust(+1, similarity, "split_feedback")


def _adjust(direction: int, similarity: float, reason: str):
    cfg = _load_config()
    state = _load_state()
    bounds = cfg["threshold_bounds"]
    step = cfg["adapt_step"]
    initial = cfg["initial_threshold"]

    current = state.get("current_threshold", initial)
    old_value = current
    new_value = max(bounds[0], min(bounds[1], current + direction * step))
    state["current_threshold"] = new_value
    state["feedback_count"] = state.get("feedback_count", 0) + 1

    history_entry = {
        "timestamp": int(time.time()),
        "direction": "down" if direction < 0 else "up",
        "reason": reason,
        "similarity": similarity,
        "old_value": round(old_value, 4),
        "new_value": round(new_value, 4),
    }
    history = state.get("history", [])
    history.append(history_entry)
    state["history"] = history
    _save_state(state)


def get_state() -> Dict:
    """Return full threshold state for diagnostics."""
    return {**_load_state(), "effective_threshold": get()}
