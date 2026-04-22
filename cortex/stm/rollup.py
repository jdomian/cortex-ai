"""STM rollup -- dense-grammar compressed summary. Ported from recall_rollup.py.

Token budget guard at lines ~145-165: strips chat/session_end rows if rollup >5200 chars.
Lazy 15-minute cache via .last-rollup-epoch file.
"""
import json
import os
import time
from collections import defaultdict, OrderedDict
from typing import Tuple, Dict, List

LEGEND = """# 72h Recall (compressed)
# LEGEND: DAYThh project verb subject outcome
#   DAY=day-of-month (0-padded), hh=24h hour (0-padded, 5-min precision dropped)
#   project=short code (first 6 chars, or mapped via CORTEX_PROJECT_MAP env var)
#   verb=one of: build|dbg|review|setup|chat|end|other
#   subject=hyphen-joined noun phrase, no articles
#   outcome=wip in-progress | ... ongoing | (blank for chat/session_end)
"""

PROJECT_MAP: dict = {
    "": "???",
    "unknown": "???",
}

# Users can override PROJECT_MAP by passing a custom map to build_rollup()
# or by setting CORTEX_PROJECT_MAP env var (JSON dict).
import json as _json
_env_map = os.environ.get("CORTEX_PROJECT_MAP", "")
if _env_map:
    try:
        PROJECT_MAP.update(_json.loads(_env_map))
    except Exception:
        pass

INTENT_TO_VERB = {
    "build": "build", "debug": "dbg", "research": "review",
    "infra": "setup", "chat": "chat", "session_end": "end", "other": "other",
}

STOPWORDS = {
    "the", "a", "an", "is", "are", "to", "of", "for", "in", "on", "at", "with",
    "please", "can", "you", "i", "want", "need", "and", "or", "but", "this", "that",
    "it", "my", "me", "be", "do", "does", "did", "get", "got", "make", "made", "have", "has",
}

import re
_word_re = re.compile(r"[A-Za-z0-9]+")

TOKEN_BUDGET_CHARS = 5200
ROLLUP_CACHE_TTL = 900  # 15 minutes


def project_code(project):
    if project in PROJECT_MAP:
        return PROJECT_MAP[project]
    return (project or "???")[:6]


def condense_subject(query_head, max_chars=35):
    if not query_head or query_head == "<session-end>":
        return ""
    words = [w.lower() for w in _word_re.findall(query_head)]
    words = [w for w in words if w not in STOPWORDS]
    if not words:
        return query_head[:max_chars].replace(" ", "-")
    out = []
    total = 0
    for w in words[:6]:
        if total + len(w) + (1 if out else 0) > max_chars:
            break
        out.append(w)
        total += len(w) + (1 if len(out) > 1 else 0)
    return "-".join(out)[:max_chars]


def fmt_line(day, hour, proj, verb, subject, outcome):
    return "{day:>2}T{hour:02d} {proj:<6} {verb:<6} {subject:<35} {outcome}".format(
        day=day, hour=hour, proj=proj[:6], verb=verb[:6], subject=subject[:35], outcome=outcome
    )


def load_events(path: str, now: int, window_hours: int = 72) -> List[Dict]:
    cutoff = now - window_hours * 3600
    events = []
    if not os.path.exists(path):
        return events
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            ep = r.get("epoch", 0)
            try:
                ep = int(ep)
            except Exception:
                continue
            if ep < cutoff:
                continue
            events.append(r)
    return events


def bucket_events(events: List[Dict]) -> OrderedDict:
    buckets = OrderedDict()
    for e in sorted(events, key=lambda r: r.get("epoch", 0)):
        ep = int(e.get("epoch", 0))
        day = time.strftime("%Y-%m-%d", time.gmtime(ep))
        key_base = (day, e.get("session_id", ""), e.get("project", ""), e.get("intent_class", "other"))
        match_key = None
        for k, v in buckets.items():
            if k[:4] == key_base and ep - v["last_ep"] <= 600:
                match_key = k
                break
        if match_key is None:
            seq = len([k for k in buckets if k[:4] == key_base])
            new_key = key_base + (seq,)
            buckets[new_key] = {
                "first_ep": ep, "last_ep": ep, "count": 1,
                "first_query": e.get("query_head", "") or "",
                "hook_types": {e.get("hook_type", "UserPromptSubmit")},
            }
        else:
            b = buckets[match_key]
            b["last_ep"] = ep
            b["count"] += 1
            b["hook_types"].add(e.get("hook_type", "UserPromptSubmit"))
    return buckets


def derive_outcome(bucket, intent_class):
    if intent_class in ("chat", "session_end"):
        return "   "
    if "Stop" in bucket["hook_types"]:
        return "wip"
    return "...  "


def build_rollup(path: str, now: int = None, window_hours: int = 72) -> Tuple[str, Dict]:
    if now is None:
        now = int(time.time())
    events = load_events(path, now, window_hours)
    buckets = bucket_events(events)
    projects = set()
    sessions = set()
    by_day = defaultdict(list)
    for key, b in buckets.items():
        day, sid, proj, intent, _seq = key
        projects.add(proj)
        sessions.add(sid)
        by_day[day].append((key, b))

    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    yesterday = time.strftime("%Y-%m-%d", time.gmtime(now - 86400))

    out = [LEGEND.rstrip(), ""]
    days_sorted = sorted(by_day.keys(), reverse=True)
    for day in days_sorted:
        rows = sorted(by_day[day], key=lambda x: x[1]["last_ep"], reverse=True)
        label = "today" if day == today else ("yesterday" if day == yesterday else "")
        header_tail = f"({label}, {len(rows)} events)" if label else f"({len(rows)} events)"
        out.append(f"## {day} {header_tail}")
        for key, b in rows:
            _, sid, proj, intent, _ = key
            last_ep = b["last_ep"]
            tm = time.gmtime(last_ep)
            day_num = tm.tm_mday
            hour = tm.tm_hour
            code = project_code(proj)
            verb = INTENT_TO_VERB.get(intent, intent[:6])
            subj = condense_subject(b["first_query"])
            if intent == "session_end":
                subj = "session-end"
            outcome = derive_outcome(b, intent)
            count_suffix = f" x{b['count']}" if b["count"] > 1 else ""
            line = fmt_line(day_num, hour, code, verb, (subj + count_suffix).strip(), outcome)
            out.append(line)
        out.append("")

    # Token-budget guard: if result >5200 chars, drop chat/session_end rows
    text = "\n".join(out).rstrip() + "\n"
    if len(text) > TOKEN_BUDGET_CHARS:
        filtered = [LEGEND.rstrip(), ""]
        for day in days_sorted:
            rows = sorted(by_day[day], key=lambda x: x[1]["last_ep"], reverse=True)
            rows = [r for r in rows if r[0][3] not in ("chat", "session_end")]
            if not rows:
                continue
            label = "today" if day == today else ("yesterday" if day == yesterday else "")
            header_tail = f"({label}, {len(rows)} events)" if label else f"({len(rows)} events)"
            filtered.append(f"## {day} {header_tail}")
            for key, b in rows:
                _, sid, proj, intent, _ = key
                tm = time.gmtime(b["last_ep"])
                code = project_code(proj)
                verb = INTENT_TO_VERB.get(intent, intent[:6])
                subj = condense_subject(b["first_query"])
                outcome = derive_outcome(b, intent)
                count_suffix = f" x{b['count']}" if b["count"] > 1 else ""
                filtered.append(fmt_line(tm.tm_mday, tm.tm_hour, code, verb, (subj + count_suffix).strip(), outcome))
            filtered.append("")
        text = "\n".join(filtered).rstrip() + "\n"

    summary = {
        "events_total": len(events),
        "projects": sorted(projects),
        "sessions": len(sessions),
        "days": days_sorted,
    }
    return text, summary


def atomic_write(path: str, text: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def rollup(path: str, summary_path: str, rollup_ep_path: str,
           force: bool = False, window_hours: int = 72) -> Tuple[str, Dict]:
    """Lazy rollup with 15-minute cache. Returns (text, meta). Writes summary_path."""
    now = int(time.time())

    # Check cache TTL (15 min = 900 seconds)
    if not force and os.path.exists(rollup_ep_path):
        try:
            with open(rollup_ep_path) as f:
                last_ep = int(f.read().strip())
            if now - last_ep < ROLLUP_CACHE_TTL:
                if os.path.exists(summary_path):
                    with open(summary_path) as f:
                        cached = f.read()
                    return cached, {"cached": True}
        except Exception:
            pass

    text, meta = build_rollup(path, now, window_hours)
    atomic_write(summary_path, text)
    atomic_write(rollup_ep_path, f"{now}\n")
    try:
        os.chmod(summary_path, 0o600)
    except Exception:
        pass
    try:
        os.chmod(rollup_ep_path, 0o600)
    except Exception:
        pass
    return text, meta
