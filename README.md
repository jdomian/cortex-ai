# cortex-ai

**Four-layer cognitive memory for AI agents.** Persistent recall across sessions, semantic search, a knowledge graph, and a learning system that evolves from your corrections. No API key required — runs locally on CPU.

```bash
pip install cortex-recall
cortex init
```

---

## What it does

AI agents have amnesia. Every new conversation starts blank. cortex-ai gives them memory that works like a brain — organized, searchable, and self-maintaining.

| Layer | Name | What it does |
|-------|------|-------------|
| L1 | **Identity** | Who the agent is, rules, personality (always loaded) |
| L2 | **Recall** | 72h deterministic short-term log + semantic search across history (on demand) |
| L3 | **Knowledge** | External docs, vendor manuals, reference material (RAG) |
| L4 | **Evolution** | Learns from corrections, promotes patterns to permanent rules |
| L5 | **Pattern Detection** | Clusters correction events using sentence-transformers, auto-promotes to feedback files |

Plus **Dream** (Default Mode Network): background maintenance that prunes the 72h log, consolidates memories, applies half-life decay, and runs L5 pattern clustering. Runs on cron. Zero token cost.

---

## How it works

cortex-ai stores memories in a local "palace" — a ChromaDB vector store plus a SQLite knowledge graph. Memories are organized into **wings** (top-level topics) and **rooms** (aspects within a topic), then auto-classified by content. Search is semantic, not keyword: ask the meaning of a thing and get matches even if the words don't line up.

The architecture is designed around how the human brain actually organizes memory — separate systems for identity, episodic recall, semantic knowledge, and procedural learning. You can read each layer independently, or combine them via the unified search interface.

---

## Quickstart

```bash
# Install
pip install cortex-recall

# One-time setup (creates ~/.cortex/ palace)
cortex init

# Mine an existing project directory into memories
cortex mine /path/to/project

# Search semantically
cortex search "how did we handle authentication?"

# See palace status
cortex status
```

---

## MCP server (for Claude Code, etc.)

cortex-ai ships an MCP (Model Context Protocol) server so AI agents can query the palace as a tool:

```bash
# Register with Claude Code
claude mcp add cortex -s user -- python -m cortex.mcp_server
```

Available tools:
- `cortex_search` — semantic search across all memories
- `cortex_status` — palace overview
- `cortex_list_wings` — top-level topics
- `cortex_list_rooms` — aspects within a wing
- `cortex_get_taxonomy` — full wing → room tree
- `cortex_check_duplicate` — avoid filing the same memory twice
- `cortex_add` — file a new memory
- `cortex_kg_add` — add a fact to the knowledge graph
- `cortex_kg_query` — query relationships
- `cortex_stm_log` — log an event to the 72h short-term memory
- `cortex_stm_fetch` — fetch and filter the 72h event log
- `cortex_dream_run` — run full nightly maintenance sweep
- `cortex_dream_consolidate` — deduplicate and compact palace memories
- `cortex_dream_decay` — apply half-life decay to memories
- `cortex_dream_patterns` — L5 pattern detection and promotion

---

## Tech stack

- **Python** 3.9+
- **ChromaDB** — vector embeddings, semantic search, local-first
- **SQLite** — knowledge graph with temporal triples
- **sentence-transformers** — `all-MiniLM-L6-v2` (runs on CPU, ~80MB model)
- **No external APIs** — everything runs on your machine

---

## What's new in v0.6.1 — Completed VectorBackend write API + thread-safe memory backends

v0.6.1 closes gaps for external adapter authors.

- **`VectorBackend.add()`, `delete()`, `upsert()`** -- the write API is now part of the ABC, so custom vector adapters (DynamoDB+OpenSearch, Postgres+pgvector) can implement the full storage contract
- **Thread-safe `Memory*Backend`** -- all memory backends use `threading.Lock`, safe for concurrent Lambda warm-container invocations
- **Logged plugin discovery** -- broken entry-point plugins log a warning to stderr instead of silently being ignored
- **Zero breaking changes** -- all v0.6.0 and v0.5.0 code works identically

---

## What's new in v0.6.0 — Pluggable Backends (Lambda-ready)

v0.6.0 cuts a storage abstraction layer so cortex-recall works on serverless runtimes like AWS Lambda, not just local machines.

**Three new interfaces** (`STMBackend`, `VectorBackend`, `KVBackend`) with built-in filesystem and in-memory implementations. External packages can register custom backends (DynamoDB, Postgres, etc.) via Python entry_points or direct call.

```python
# Works on Lambda -- no filesystem, no ChromaDB cold-start
from cortex.stm import STM
from cortex.backends.memory import MemorySTMBackend

stm = STM(backend=MemorySTMBackend())
stm.log({"epoch": 1234567890, "project": "my-lambda", "query_head": "hi"})

# Dream nightly maintenance with memory backends
from cortex.dream import Dream
from cortex.backends.memory import MemoryVectorBackend, MemorySTMBackend, MemoryKVBackend

dream = Dream(
    vector_backend=MemoryVectorBackend(),
    stm_backend=MemorySTMBackend(),
    kv_backend=MemoryKVBackend(),
)
result = dream.run()
```

**Zero breaking changes** -- all v0.5.0 code works identically. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full guide.

---

## License & attribution

MIT License. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

cortex-ai is a fork of [MemPalace](https://github.com/milla-jovovich/mempalace) by milla-jovovich. The MemPalace engine — ChromaDB-backed search, knowledge graph, palace structure, miner system — is the foundation. cortex-ai adds the four-layer cognitive architecture, MCP server interface, hooks integration, and onboarding flow on top.

---

## Status

cortex-ai v0.6.1 is in beta. Issues welcome at https://github.com/jdomian/cortex-ai/issues.
