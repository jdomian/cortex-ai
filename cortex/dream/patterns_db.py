"""Pattern index -- JSONL-backed pattern store with fcntl.flock for safe concurrent writes."""
import fcntl
import json
import os
import time
from typing import Dict, List, Optional


def _default_db_path():
    return os.path.expanduser("~/.cortex/l5/patterns.jsonl")


def _ensure_dir(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def all_patterns(db_path: str = None) -> List[Dict]:
    if db_path is None:
        db_path = _default_db_path()
    if not os.path.exists(db_path):
        return []
    patterns = []
    with open(db_path) as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                patterns.append(json.loads(s))
            except Exception:
                continue
    return patterns


def get_pattern(pattern_id: str, db_path: str = None) -> Optional[Dict]:
    for p in all_patterns(db_path):
        if p.get("pattern_id") == pattern_id:
            return p
    return None


def put_pattern(pattern: Dict, db_path: str = None):
    """Upsert a pattern (replace if pattern_id matches, append if new). Uses flock."""
    if db_path is None:
        db_path = _default_db_path()
    _ensure_dir(db_path)
    lock_path = db_path + ".lock"

    with open(lock_path, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        existing = all_patterns(db_path)
        pid = pattern["pattern_id"]
        updated = [pattern if p["pattern_id"] == pid else p for p in existing]
        if not any(p["pattern_id"] == pid for p in existing):
            updated.append(pattern)
        tmp = db_path + ".tmp"
        with open(tmp, "w") as f:
            for p in updated:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        os.replace(tmp, db_path)
        try:
            os.chmod(db_path, 0o600)
        except Exception:
            pass


def delete_pattern(pattern_id: str, db_path: str = None):
    if db_path is None:
        db_path = _default_db_path()
    if not os.path.exists(db_path):
        return
    lock_path = db_path + ".lock"
    with open(lock_path, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        existing = all_patterns(db_path)
        remaining = [p for p in existing if p.get("pattern_id") != pattern_id]
        tmp = db_path + ".tmp"
        with open(tmp, "w") as f:
            for p in remaining:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        os.replace(tmp, db_path)
