"""CLI dispatcher for 'cortex stm' subcommand."""
import argparse
import json
import sys
import time

from cortex.stm import STM


def cmd_stm(args):
    stm = STM()

    sub = getattr(args, "stm_command", None)
    if sub == "log":
        event = {
            "epoch": int(time.time()),
            "project": getattr(args, "project", "") or "",
            "session_id": getattr(args, "session_id", "") or "",
            "intent_class": getattr(args, "intent", "") or "other",
            "query_head": getattr(args, "query", "") or "",
            "hook_type": "manual",
        }
        ok = stm.log(event)
        print(json.dumps({"logged": ok}))

    elif sub == "fetch":
        filters = {}
        for k in ("project", "day", "session", "intent"):
            v = getattr(args, k, None)
            if v:
                filters[k] = v
        events = stm.fetch(**filters)
        if getattr(args, "json", False):
            for e in events:
                print(json.dumps(e, ensure_ascii=False))
        else:
            from cortex.stm.fetch import emit_markdown
            sys.stdout.write(emit_markdown(events, full=getattr(args, "full", False)))

    elif sub == "rollup":
        text = stm.rollup(force=getattr(args, "force", False))
        sys.stdout.write(text)

    elif sub == "prune":
        result = stm.prune()
        print(f"prune ok: kept={result['kept']} dropped={result['dropped']}")

    else:
        print("Usage: cortex stm {log,fetch,rollup,prune}")
        return 1
    return 0


def add_stm_subparser(sub):
    p_stm = sub.add_parser("stm", help="Short-term memory (72h recall)")
    stm_sub = p_stm.add_subparsers(dest="stm_command")

    p_log = stm_sub.add_parser("log", help="Append an event manually")
    p_log.add_argument("--project", default="")
    p_log.add_argument("--session-id", default="")
    p_log.add_argument("--intent", default="other")
    p_log.add_argument("--query", default="")

    p_fetch = stm_sub.add_parser("fetch", help="Query events from the 72h log")
    p_fetch.add_argument("--project")
    p_fetch.add_argument("--day", help="YYYY-MM-DD")
    p_fetch.add_argument("--session")
    p_fetch.add_argument("--intent")
    p_fetch.add_argument("--full", action="store_true")
    p_fetch.add_argument("--json", action="store_true")

    p_rollup = stm_sub.add_parser("rollup", help="Generate compressed summary")
    p_rollup.add_argument("--force", action="store_true", help="Bypass 15-min cache")

    stm_sub.add_parser("prune", help="Drop events older than 72h")

    return p_stm
