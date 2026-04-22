"""STM event fetcher. Ported from recall_fetch.py."""
import json
import os
import sys
import time
from collections import defaultdict
from typing import List, Dict, Optional


def fetch(path: str, project: str = None, day: str = None,
          session: str = None, intent: str = None,
          window_hours: int = 72) -> List[Dict]:
    """Load events from JSONL, filtering by window and optional criteria."""
    now = int(time.time())
    cutoff = now - window_hours * 3600
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                r = json.loads(s)
            except Exception:
                continue
            ep = int(r.get("epoch", 0) or 0)
            if ep < cutoff:
                continue
            if project and r.get("project", "") != project:
                continue
            if day and time.strftime("%Y-%m-%d", time.gmtime(ep)) != day:
                continue
            if session and r.get("session_id", "") != session:
                continue
            if intent and r.get("intent_class", "") != intent:
                continue
            out.append(r)
    return out


def emit_markdown(events: List[Dict], full: bool = False) -> str:
    if not events:
        return "_(no matching events)_\n"
    by_day = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in events:
        ep = int(r.get("epoch", 0) or 0)
        day = time.strftime("%Y-%m-%d", time.gmtime(ep))
        by_day[day][r.get("project", "unknown")][r.get("session_id", "?")].append(r)
    lines = []
    for day in sorted(by_day.keys(), reverse=True):
        lines.append(f"## {day}")
        for proj, sessions in sorted(by_day[day].items()):
            lines.append(f"### {proj}")
            for sid, items in sessions.items():
                lines.append(f"- session `{sid[:8]}` ({len(items)} events)")
                for r in items[:8]:
                    tm = time.strftime("%H:%M", time.gmtime(int(r.get("epoch", 0) or 0)))
                    lines.append(f"  - {tm} `{r.get('intent_class', '?')}` -- {r.get('query_head', '')}")
                if len(items) > 8:
                    lines.append(f"  - ... +{len(items) - 8} more")
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    if not full and len(text) > 2000:
        text = text[:2000].rstrip() + "\n\n... (truncated, use --full for more)\n"
    return text


def emit_jsonl(events: List[Dict]) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in events) + ("\n" if events else "")


def cmd_stm_fetch(args, path: str, summary_path: str = None, window_hours: int = 72):
    """CLI dispatch for 'cortex stm fetch'."""
    filters = {k: v for k, v in vars(args).items()
               if k in ("project", "day", "session", "intent") and v}

    if not filters and not getattr(args, "json", False):
        if summary_path and os.path.exists(summary_path):
            with open(summary_path) as f:
                sys.stdout.write(f.read())
            return 0

    events = fetch(path, **{k: v for k, v in filters.items()}, window_hours=window_hours)
    if getattr(args, "json", False):
        sys.stdout.write(emit_jsonl(events))
    else:
        sys.stdout.write(emit_markdown(events, full=getattr(args, "full", False)))
    return 0
