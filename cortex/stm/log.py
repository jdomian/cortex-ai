"""STM event writer. Appends JSON lines to the 72h event log."""
import json
import os
import time
from .classifier import filter_secret, increment_drops


def log(event: dict, path: str, drops_file: str = None) -> bool:
    """Append a single event to the JSONL log. Returns True if written, False if filtered/error."""
    try:
        query = event.get("query_head", "") or ""
        filtered = filter_secret(query)
        if filtered is None:
            increment_drops(drops_file)
            return False
        event = dict(event)
        event["query_head"] = filtered

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        line = json.dumps(event, ensure_ascii=False)
        with open(path, "a") as f:
            f.write(line + "\n")
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False
