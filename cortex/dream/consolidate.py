"""Dream step: L3 consolidation -- find orphaned ChromaDB entries and dedup by content hash.

Adapted from session-sweeper.py logic. Identifies idle transcript sessions
not yet saved to Cortex and marks them for follow-up.
"""
import hashlib
import os
import time
from typing import Dict, Optional


def run(palace_path: str = None, idle_threshold_hours: int = 1,
        collection_name: str = None) -> Dict:
    """Scan for orphaned session transcripts older than threshold. Returns stats."""
    projects_dir = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(projects_dir):
        return {"step": "consolidate", "orphaned": 0, "message": "projects dir not found"}

    now = time.time()
    threshold_seconds = idle_threshold_hours * 3600
    orphaned = []

    for project_dir in os.listdir(projects_dir):
        project_path = os.path.join(projects_dir, project_dir)
        if not os.path.isdir(project_path):
            continue
        for entry in os.listdir(project_path):
            if not entry.endswith(".jsonl"):
                continue
            filepath = os.path.join(project_path, entry)
            try:
                mtime = os.path.getmtime(filepath)
                age = now - mtime
                if age >= threshold_seconds:
                    session_id = entry.replace(".jsonl", "")
                    orphaned.append({"session_id": session_id, "age_hours": round(age / 3600, 1)})
            except Exception:
                continue

    already_saved = _get_saved_session_ids(palace_path, collection_name)
    unsaved = [t for t in orphaned if t["session_id"] not in already_saved]

    return {
        "step": "consolidate",
        "idle_sessions_found": len(orphaned),
        "already_in_cortex": len(orphaned) - len(unsaved),
        "unsaved": len(unsaved),
        "unsaved_ids": [t["session_id"][:8] for t in unsaved[:5]],
    }


def _get_saved_session_ids(palace_path: str = None, collection_name: str = None):
    try:
        import chromadb
        if palace_path is None:
            palace_path = os.path.expanduser("~/.cortex/palace")
        if collection_name is None:
            collection_name = "memories"
        client = chromadb.PersistentClient(path=palace_path)
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            return set()
        results = collection.get(where={"wing": "sessions"}, include=["metadatas"])
        saved = set()
        if results.get("metadatas"):
            for meta in results["metadatas"]:
                sid = meta.get("session_id", "")
                if sid:
                    saved.add(sid)
        return saved
    except Exception:
        return set()
