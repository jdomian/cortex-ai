"""CLI dispatcher for 'cortex dream' subcommand."""
import json
import sys

from cortex.dream import Dream
from cortex.dream import consolidate, decay, cron
from cortex.dream import threshold


def cmd_dream(args):
    sub = getattr(args, "dream_command", None)

    if sub == "run":
        result = Dream().run()
        print(json.dumps(result, indent=2))

    elif sub == "consolidate":
        result = consolidate.run()
        print(json.dumps(result, indent=2))

    elif sub == "decay":
        result = decay.run()
        print(json.dumps(result, indent=2))

    elif sub == "patterns":
        _handle_patterns(args)

    elif sub == "install-cron":
        schedule = getattr(args, "schedule", "0 3 * * *")
        line = cron.install_cron(schedule=schedule)
        print(f"Cron installed: {line}")

    elif sub == "threshold":
        state = threshold.get_state()
        print(json.dumps(state, indent=2))

    else:
        print("Usage: cortex dream {run,consolidate,decay,patterns,install-cron,threshold}")
        return 1
    return 0


def _handle_patterns(args):
    from cortex.dream import patterns
    pat_sub = getattr(args, "patterns_command", None)

    if pat_sub == "list":
        from cortex.dream.patterns_db import all_patterns
        pats = all_patterns()
        active = [p for p in pats if not p.get("retired")]
        for p in active:
            promoted = " [PROMOTED]" if p.get("promoted") else ""
            stale = " [STALE]" if p.get("stale") else ""
            print(f"  {p['pattern_id']} (n={p.get('occurrence_count',0)}){promoted}{stale}")

    elif pat_sub == "show":
        from cortex.dream.patterns_db import get_pattern
        pid = getattr(args, "pattern_id", None)
        p = get_pattern(pid)
        if p:
            centroid = p.pop("cluster_centroid", None)
            print(json.dumps(p, indent=2))
            if centroid:
                print(f"  cluster_centroid: [{len(centroid)}-dim vector]")
        else:
            print(f"Pattern not found: {pid}")

    elif pat_sub == "merge":
        id1 = getattr(args, "id1", None)
        id2 = getattr(args, "id2", None)
        result = patterns.merge_patterns(id1, id2)
        print(json.dumps(result, indent=2))

    elif pat_sub == "split":
        pid = getattr(args, "pattern_id", None)
        result = patterns.split_pattern(pid)
        print(json.dumps(result, indent=2))

    elif pat_sub == "retire":
        pid = getattr(args, "pattern_id", None)
        result = patterns.retire_pattern(pid)
        print(json.dumps(result, indent=2))

    else:
        print("Usage: cortex dream patterns {list,show,merge,split,retire}")


def add_dream_subparser(sub):
    p_dream = sub.add_parser("dream", help="Cross-cutting memory maintenance")
    dream_sub = p_dream.add_subparsers(dest="dream_command")

    dream_sub.add_parser("run", help="Run all maintenance sweeps")
    dream_sub.add_parser("consolidate", help="L3 consolidation only")
    dream_sub.add_parser("decay", help="L3 age-out only")

    p_pat = dream_sub.add_parser("patterns", help="L5 pattern management")
    pat_sub = p_pat.add_subparsers(dest="patterns_command")
    pat_sub.add_parser("list", help="List active patterns")

    p_show = pat_sub.add_parser("show", help="Show pattern details")
    p_show.add_argument("pattern_id")

    p_merge = pat_sub.add_parser("merge", help="Merge two patterns (user feedback A)")
    p_merge.add_argument("id1")
    p_merge.add_argument("id2")

    p_split = pat_sub.add_parser("split", help="Split an incoherent pattern (user feedback B)")
    p_split.add_argument("pattern_id")

    p_retire = pat_sub.add_parser("retire", help="Manually retire a pattern")
    p_retire.add_argument("pattern_id")

    p_cron = dream_sub.add_parser("install-cron", help="Install nightly cron")
    p_cron.add_argument("--schedule", default="0 3 * * *", help="Cron schedule (default: 3 AM)")

    dream_sub.add_parser("threshold", help="Show adaptive threshold state")

    return p_dream
