"""Secret filter + intent classifier.

v0.6.0 (2026-05-04): expanded _INTENT_RULES to handle more verbs and
PostToolUse action summaries (write:, bash:, cortex_add:, gmail_send:, etc).
Old rules kept; new rules layered on top with order = priority.
"""
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

# Intent rules — first match wins, so order matters (specific → general).
# Action summaries from PostToolUse (e.g. "cortex_add:wing=...", "gmail_send:to=...")
# are checked first because they're high-signal and short.
_INTENT_RULES = [
    # ─── PostToolUse action summaries (highest signal) ────────────────────
    (re.compile(r"^cortex_(add|kg|stm_log)", re.IGNORECASE),                "memory"),
    (re.compile(r"^gmail_(send|draft)|^cal_(create|delete|update)", re.IGNORECASE), "comms"),
    (re.compile(r"^write:|^edit:", re.IGNORECASE),                          "build"),
    (re.compile(r"^webfetch:|^websearch:", re.IGNORECASE),                  "research"),
    (re.compile(r"^agent:|^task_create:", re.IGNORECASE),                   "delegate"),
    (re.compile(r"^bash:.*\b(git\s+(commit|push|tag)|gh\s+pr|terraform\s+(apply|plan)|aws\s+|kubectl|docker\s+(build|push|run)|systemctl|ssh|sudo)\b", re.IGNORECASE), "infra"),
    (re.compile(r"^bash:.*\b(test|pytest|jest|vitest|npm\s+test|go\s+test|cargo\s+test)\b", re.IGNORECASE), "test"),
    (re.compile(r"^bash:.*\b(plane|mslist|sync|apply)\b", re.IGNORECASE),   "build"),

    # ─── User prompt verb-based ──────────────────────────────────────────
    (re.compile(r"\b(fix(ed|ing)?|debug|broken|bug|crash|error|fail(ed|ing)?|doesn'?t work|not working)\b", re.IGNORECASE), "debug"),
    (re.compile(r"/auto-(plan|build|execute)\b", re.IGNORECASE),            "build"),
    (re.compile(r"\b(build|built|deploy|implement|ship|create(d)?|make|made|wrote|writing|add|added|set up|configure)\b", re.IGNORECASE), "build"),
    (re.compile(r"\b(plan(ning)?|let'?s|tomorrow|next|what'?s.*left|what.*next|todo)\b", re.IGNORECASE), "plan"),
    (re.compile(r"\b(review|check|verify|audit|look at|inspect|examine|confirm)\b", re.IGNORECASE), "review"),
    (re.compile(r"\b(test(ing)?|run|smoke|validate)\b", re.IGNORECASE),     "test"),
    (re.compile(r"\b(grep|search|find|look\s+up|cortex_search|research)\b", re.IGNORECASE), "research"),
    (re.compile(r"\b(send|reply|draft|email|message|tell|notify)\b", re.IGNORECASE), "comms"),
    (re.compile(r"\b(remember|save|note|track|log|store)\b", re.IGNORECASE), "memory"),
    (re.compile(r"\b(ssh|docker|systemctl|sudo|cron|ufw|terraform|aws|kubectl|10\.0\.0\.)\b", re.IGNORECASE), "infra"),
    (re.compile(r"\b(refactor|cleanup|reorganize|rename|extract|consolidate)\b", re.IGNORECASE), "refactor"),
    (re.compile(r"\b(read|show|display|print|cat|view|see|list)\b", re.IGNORECASE), "read"),
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
        if query_head == "<turn-end>":
            return "turn_end"
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
