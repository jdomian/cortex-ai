"""STM prune -- fcntl.flock atomic drop of events older than window. Ported from recall_prune.py."""
import fcntl
import json
import os
import time
from typing import Tuple


def prune(path: str, lock_path: str, prune_ep_path: str,
          older_than_hours: int = 72) -> Tuple[int, int]:
    """Remove events older than older_than_hours. Returns (kept, dropped)."""
    now = int(time.time())
    cutoff = now - older_than_hours * 3600
    if not os.path.exists(path):
        return 0, 0

    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    with open(lock_path, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        tmp = path + ".tmp"
        kept = 0
        dropped = 0
        with open(path) as src, open(tmp, "w") as dst:
            for line in src:
                s = line.strip()
                if not s:
                    continue
                try:
                    r = json.loads(s)
                except Exception:
                    dropped += 1
                    continue
                ep = int(r.get("epoch", 0) or 0)
                if ep < cutoff:
                    dropped += 1
                    continue
                dst.write(line if line.endswith("\n") else line + "\n")
                kept += 1
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        try:
            os.makedirs(os.path.dirname(os.path.abspath(prune_ep_path)), exist_ok=True)
            with open(prune_ep_path, "w") as f:
                f.write(f"{now}\n")
            os.chmod(prune_ep_path, 0o600)
        except Exception:
            pass
    return kept, dropped
