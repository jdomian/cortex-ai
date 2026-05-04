# STM v0.6.0 — Sticky Project + Action Capture

**Shipped 2026-05-04.** Three improvements to the L2 Recall short-term memory (72h ring) so future sessions can recall what actually happened, not just what was asked.

## The problem (observed 2026-05-04 22:30 CDT)

Reviewing tonight's STM trace showed three weaknesses in the recall capture:

1. **`project` was `basename(cwd)`** — brittle. A 4-hour KPMG conversation got tagged across `kpmg`, `landing-zone`, `tmp`, `claude`, and `forge` because the user `cd`-ed into different paths and multi-project sessions blurred together. Filtering STM by `project=kpmg` missed chunks of the same workstream.
2. **PostToolUse and Stop hooks both emitted `<turn-end>`** — meaning every assistant action (file writes, bash commands, cortex_add calls, gmail_send, calendar_create) was completely invisible to STM. Future sessions saw "okay update plane" without ever knowing 10 work items got synced.
3. **`classify_intent` only had 4 patterns** (build / debug / research / infra) — and they were narrow. Tonight's 109 STM events all classified as `other`. Filtering by intent surfaced nothing.

## The fix — three layers

### Fix 1: Sticky project resolution

`recall-capture.sh:21` changed from `os.path.basename(cwd)` to a 3-tier resolution:

```python
project = os.environ.get("CLAUDE_PROJECT") \
       or path_prefix_lookup(cwd, PATH_PREFIX_TO_PROJECT) \
       or os.path.basename(cwd) \
       or "unknown"
```

`PATH_PREFIX_TO_PROJECT` is a deterministic table at the top of the hook — 18 prefixes covering the host's known projects (kpmg, simcity, flipper, ada, cortex, jobhunt, budget, secretary, forge, clsrv). Path-prefix lookup is order-sensitive (longest prefixes first) so `/home/claude/kpmg/landing-zone` resolves to `kpmg`, not `landing-zone`.

### Fix 2: Action capture in PostToolUse

`recall-capture.sh` now extracts a real summary from PostToolUse events instead of writing `<turn-end>`. The `action_summary()` function maps tool name + tool_input → a short string:

| Tool | Output shape | Example |
|------|--------------|---------|
| Write | `write:<path>` | `write:/home/claude/kpmg/landing-zone-status.md` |
| Edit  | `edit:<path>` | `edit:/home/claude/.claude/scripts/plane_lib.py` |
| Bash  | `bash:<cmd>` | `bash:python3 mslist-to-plane.py --apply` |
| `cortex_add` | `cortex_add:wing=X/room=Y` | `cortex_add:wing=kpmg/room=tooling` |
| `cortex_kg_add` | `cortex_kg:<subj> <pred> <obj>` | — |
| `gmail_send` | `gmail_send:to=X subj=Y` | `gmail_send:to=phua@the.team subj=RE: Okta` |
| `calendar_create` | `cal_create:<title> start=<iso>` | — |
| `WebFetch` / `WebSearch` | `webfetch:<url>` / `websearch:<q>` | — |
| `Agent` | `agent:<type> <description>` | `agent:debugger investigate-build-failure` |

Skipped tools: `Read`, `Glob`, `Grep`, `ToolSearch`, MCP resource list/read.
Skipped Bash heads: `ls`, `cat`, `head`, `tail`, `wc`, `pwd`, `echo`, `grep`, `find`, `which`, `stat`, `diff`, `file`, `xxd`. (Read-style commands; too noisy.)

All output runs through existing `filter_secret()` so credential strings still drop.

### Fix 3: Expanded intent classifier (`cortex/stm/classifier.py`)

`_INTENT_RULES` grew from 4 patterns to 18, ordered specific → general:

- **Action-summary patterns first** (highest signal, e.g. `^cortex_(add|kg|stm_log)` → `memory`)
- **Verb-based user-prompt patterns next** (e.g. `\b(build|built|wrote|created|implement)\b` → `build`)
- **Domain patterns last** (`\b(ssh|docker|terraform|aws)\b` → `infra`)

New intents added to the vocabulary: `memory`, `comms`, `delegate`, `refactor`, `read`, `plan`, `test`. Existing intents (`build`, `debug`, `research`, `infra`, `other`) preserved.

`<turn-end>` markers now classify as `turn_end` instead of `other` so they're filterable out of summaries.

## Smoke test (post-deploy 2026-05-04)

```
UserPromptSubmit  proj=kpmg      intent=debug   qh=fix the plane sync
PostToolUse       proj=kpmg      intent=build   qh=write:/home/claude/.claude/scripts/mslist-to-plane.py
PostToolUse       proj=kpmg      intent=infra   qh=bash:git push origin dev
PostToolUse       proj=cortex    intent=memory  qh=cortex_add:wing=kpmg/room=tooling
PostToolUse       proj=claude    intent=comms   qh=gmail_send:to=phua@the.team subj=RE: Okta test
UserPromptSubmit  proj=kpmg      intent=plan    qh=what is left for tomorrow morning
UserPromptSubmit  proj=kpmg      intent=comms   qh=send the email to peter hua
```

All projects resolve correctly, all actions captured with summaries, all intents classify into useful buckets.

## Files changed

- `~/.claude/hooks/recall-capture.sh` — full rewrite, ~150 lines (was 64). Backup at `recall-capture.sh.bak.20260504`.
- `cortex-ai/cortex/stm/classifier.py` — `_INTENT_RULES` + `classify_intent()` updated. Backup at `classifier.py.bak.20260504`.
- No DB schema changes. No memory file changes. 72h.jsonl format unchanged (additive).

## What's next (future work — see prompt below)

Things we considered but didn't ship tonight:

1. **End-of-turn assistant summary.** Have the assistant emit a 1-line "what I just did" after each meaningful turn via `cortex_stm_log`. Could be enforced by a Stop hook that reads `transcript_path` and synthesizes a summary. Requires either Claude-side cooperation or a small classifier. Worth exploring once Cortex grows beyond claude-server.
2. **Aggregation in `recall_rollup.py`.** Cluster nearby STM entries by project + topic, deduplicate verbatim repeats, pull file paths into a separate "artifacts" section. The current `x43` notation means a verbatim line repeated 43 times — useful but lossy. A smarter rollup could surface the **actions** taken vs the **questions** asked.
3. **Per-project sensitivity tagging.** KPMG STM entries should never leak into a public Cortex export. Add `sensitive=true` to the event dict for entries where project is in a configured "sensitive" list.
4. **PostToolUse capture for tool errors.** Right now we capture inputs only. If a tool returned an error, that's high-signal — should land in STM with `intent=debug`.

## Prompt for revisiting (paste into a future session)

```
Continue the STM v0.6.0 improvements work documented in
docs/STM-v0.6.0-IMPROVEMENTS.md. Goals from the "What's next" section:

1. End-of-turn assistant summary via Stop hook + cortex_stm_log.
2. Smarter recall_rollup.py aggregation (cluster by project + topic, dedupe,
   pull artifacts into separate section).
3. Per-project sensitivity tagging on STM events.
4. PostToolUse capture for tool errors with intent=debug.

Read the existing recall-capture.sh and classifier.py first. Confirm with me
before changing the public cortex.stm API surface. Run smoke tests after each
fix using the pattern in the doc's "Smoke test" section.
```

## Why this matters for Cortex as a product

Cortex's L2 Recall is the layer most exposed to users — every session reads it on bootstrap. If the signal-to-noise ratio is poor, the whole memory system feels broken regardless of how good L4 evolution is. These three fixes are local to one self-hosted instance, but the patterns (sticky project, action capture in hooks, expanded intent rules) are upstream-worthy. Consider folding back into the cortex-recall package after a few weeks of dogfooding.
