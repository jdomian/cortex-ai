"""Secret filter + intent classifier. Ported verbatim from recall_lib.py."""
import os
import re
import hashlib
from typing import Optional

DROPS_FILE_DEFAULT = os.path.expanduser("~/.cortex/stm/.secret-filter-drops")

_SECRET_PATTERNS = [
    re.compile(r"password\s*=", re.IGNORECASE),
    re.compile(r"api[_-]?key\s*=", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"[A-Fa-f0-9]{32,}"),
    re.compile(r"(?:[A-Z_]+KEY|TOKEN|SECRET)\s*=\s*[\"']?[^\s\"']+"),
]

_INTENT_RULES = [
    (re.compile(r"/auto-(plan|build)|\bbuild\b|\bdeploy\b|\bimplement\b|\bship\b", re.IGNORECASE), "build"),
    (re.compile(r"\berror\b|\bfail(ed|ing)?\b|\bbroken\b|\bbug\b|\bcrash\b|\bdoesn\'?t work\b", re.IGNORECASE), "debug"),
    (re.compile(r"\bgrep\b|\bsearch\b|\bfind\b|\blook\s+up\b|\bcortex_search\b|\bresearch\b", re.IGNORECASE), "research"),
    (re.compile(r"\bssh\b|\bdocker\b|\bsystemctl\b|\bsudo\b|\bcron\b|\bufw\b|\b10\.0\.0\.", re.IGNORECASE), "infra"),
]

SESSION_END_MARKER = "<session-end>"


def filter_secret(text):
    try:
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                return None
        return text
    except Exception:
        return None


def classify_intent(query_head):
    try:
        if query_head == SESSION_END_MARKER:
            return "session_end"
        for pat, cls in _INTENT_RULES:
            if pat.search(query_head or ""):
                return cls
        return "other"
    except Exception:
        return "other"


def increment_drops(drops_file=None):
    if drops_file is None:
        drops_file = DROPS_FILE_DEFAULT
    try:
        os.makedirs(os.path.dirname(drops_file), exist_ok=True)
        cur = 0
        if os.path.exists(drops_file):
            try:
                with open(drops_file) as f:
                    cur = int((f.read() or "0").strip())
            except Exception:
                cur = 0
        with open(drops_file, "w") as f:
            f.write(str(cur + 1) + "\n")
        try:
            os.chmod(drops_file, 0o600)
        except Exception:
            pass
    except Exception:
        pass


def compute_dedup_key(session_id, epoch, hook_type):
    return hashlib.sha1(f"{session_id}|{epoch}|{hook_type}".encode("utf-8")).hexdigest()
