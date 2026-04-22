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
| L2 | **Recall** | Semantic search across everything that happened (on demand) |
| L3 | **Knowledge** | External docs, vendor manuals, reference material (RAG) |
| L4 | **Evolution** | Learns from corrections, promotes patterns to permanent rules |

Plus **DMN** (Default Mode Network): background maintenance that consolidates memories, deduplicates, detects patterns, and manages decay. Runs on cron. Zero token cost.

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

---

## Tech stack

- **Python** 3.9+
- **ChromaDB** — vector embeddings, semantic search, local-first
- **SQLite** — knowledge graph with temporal triples
- **sentence-transformers** — `all-MiniLM-L6-v2` (runs on CPU, ~80MB model)
- **No external APIs** — everything runs on your machine

---

## License & attribution

MIT License. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

cortex-ai is a fork of [MemPalace](https://github.com/milla-jovovich/mempalace) by milla-jovovich. The MemPalace engine — ChromaDB-backed search, knowledge graph, palace structure, miner system — is the foundation. cortex-ai adds the four-layer cognitive architecture, MCP server interface, hooks integration, and onboarding flow on top.

---

## Status

cortex-ai v0.4.0 is the first public release. Beta. Expect rough edges. Issues welcome at https://github.com/jdomian/cortex-ai/issues.
