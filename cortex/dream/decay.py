"""Dream step: L3 age-out via half-life decay on ChromaDB metadata weights."""
import math
import os
import time
from typing import Dict


def run(palace_path: str = None, collection_name: str = None,
        half_life_days: int = 30, vector=None) -> Dict:
    """Apply decay factor to memories based on last_accessed metadata.

    v0.5.0 kwargs palace_path and collection_name are preserved for back-compat.
    New in v0.6.0: optional `vector` backend. When provided, palace_path and
    collection_name are ignored for the ChromaDB lookup.
    """
    if vector is not None:
        return _run_with_backend(vector, half_life_days)
    return _run_filesystem(palace_path, collection_name, half_life_days)


def _run_with_backend(vector, half_life_days: int) -> Dict:
    try:
        result = vector.get_all(include=["metadatas"])
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])

        if not metadatas:
            return {"step": "decay", "updated": 0}

        now = time.time()
        half_life_seconds = half_life_days * 86400
        updated = 0
        ids_to_update = []
        new_metadatas = []

        for i, meta in enumerate(metadatas):
            last_accessed = meta.get("last_accessed")
            if last_accessed is None:
                continue
            try:
                last_ts = float(last_accessed)
            except Exception:
                continue
            age_seconds = now - last_ts
            decay_factor = math.pow(0.5, age_seconds / half_life_seconds)
            current_decay = float(meta.get("decay_factor", 1.0))
            new_decay = round(current_decay * decay_factor, 6)
            if abs(new_decay - current_decay) > 0.001:
                updated_meta = dict(meta)
                updated_meta["decay_factor"] = new_decay
                ids_to_update.append(ids[i])
                new_metadatas.append(updated_meta)
                updated += 1

        if ids_to_update:
            vector.update_metadata(ids_to_update, new_metadatas)

        return {"step": "decay", "updated": updated, "half_life_days": half_life_days}
    except Exception as e:
        return {"step": "decay", "updated": 0, "error": str(e)}


def _run_filesystem(palace_path: str, collection_name: str,
                    half_life_days: int) -> Dict:
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
            return {"step": "decay", "updated": 0, "message": "no collection"}

        results = collection.get(include=["metadatas"])
        if not results.get("metadatas"):
            return {"step": "decay", "updated": 0}

        all_results = collection.get()
        ids = all_results.get("ids", [])
        metadatas = results.get("metadatas", [])

        if len(ids) != len(metadatas):
            return {"step": "decay", "updated": 0, "message": "id/metadata count mismatch"}

        now = time.time()
        half_life_seconds = half_life_days * 86400
        updated = 0
        ids_to_update = []
        new_metadatas = []

        for i, meta in enumerate(metadatas):
            last_accessed = meta.get("last_accessed")
            if last_accessed is None:
                continue
            try:
                last_ts = float(last_accessed)
            except Exception:
                continue
            age_seconds = now - last_ts
            decay_factor = math.pow(0.5, age_seconds / half_life_seconds)
            current_decay = float(meta.get("decay_factor", 1.0))
            new_decay = round(current_decay * decay_factor, 6)
            if abs(new_decay - current_decay) > 0.001:
                updated_meta = dict(meta)
                updated_meta["decay_factor"] = new_decay
                ids_to_update.append(ids[i])
                new_metadatas.append(updated_meta)
                updated += 1

        if ids_to_update:
            collection.update(ids=ids_to_update, metadatas=new_metadatas)

        return {"step": "decay", "updated": updated, "half_life_days": half_life_days}

    except Exception as e:
        return {"step": "decay", "updated": 0, "error": str(e)}
