# Changelog

All notable changes to cortex-ai will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] — 2026-04-23

### Added
- `cortex.backends` package with pluggable STM / Vector / KV interfaces
- `FilesystemSTMBackend`, `FilesystemVectorBackend`, `FilesystemKVBackend` (default, matches v0.5.0 behavior)
- `MemorySTMBackend`, `MemoryVectorBackend`, `MemoryKVBackend` (for tests and stateless environments)
- Backend registry with `get_backend()` and `register_backend()` for third-party plugins
- `load_config()` and `get_backend_config()` in `cortex/config.py` -- YAML config loader for `~/.cortex/config.yaml`
- `CORTEX_CONFIG_PATH` env var -- overrides default `~/.cortex/config.yaml` location (Lambda-friendly)
- `docs/DEPLOYMENT.md` -- filesystem, serverless, and custom-backend deployment guide
- `docs/BACKENDS.md` -- backend interface reference

### Changed
- `STM.__init__` accepts optional `backend=` parameter (default: filesystem, matches v0.5.0)
- `Dream.__init__` accepts optional `vector_backend=`, `stm_backend=`, `kv_backend=` parameters (default: filesystem)
- Dream step modules (`consolidate`, `decay`, `patterns`, `prune_72h`) accept backend params; default behavior unchanged

### Unchanged / Back-compat
- All v0.5.0 public APIs work identically -- no code changes required for existing installs
- Default storage is still `~/.cortex/stm/72h.jsonl` + `~/.cortex/palace/` (ChromaDB)
- No new required dependencies; `pyyaml` is already pinned from v0.5.0

## [0.5.0] — 2026-04-22

### Added
- `cortex.stm` — deterministic 72h short-term memory: JSONL event log, rolling rollup, secret filter, atomic prune via `fcntl.flock`
- `cortex.dream` — nightly maintenance orchestrator: prune, consolidate, half-life decay, L5 pattern detection
- L5 REAL pattern detection: correction event capture, sentence-transformers cosine similarity clustering, adaptive threshold, auto-promotion to feedback rule files
- 6 new MCP tools: `cortex_stm_log`, `cortex_stm_fetch`, `cortex_dream_run`, `cortex_dream_consolidate`, `cortex_dream_decay`, `cortex_dream_patterns`
- CLI subcommands: `cortex stm fetch`, `cortex stm rollup`, `cortex stm prune`, `cortex dream run`, `cortex dream decay`
- Tests shipped in wheel (53 total, including fixtures)
- `sentence-transformers>=2.2,<4` added as a dependency

## [0.4.0] — 2026-04-22

First public release.

### Added
- Four-layer cognitive memory architecture (Identity, Recall, Knowledge, Evolution)
- MCP server with `cortex_*` tool surface for Claude Code and other MCP clients
- ChromaDB-backed semantic search across memories
- SQLite knowledge graph with temporal triples
- Palace organization: wings (topics) → rooms (aspects) → drawers (memories)
- Miner: project directory → memories
- Convo miner: chat transcripts → memories
- Entity detector + registry
- Default Mode Network (DMN) maintenance scripts (consolidation, deduplication, decay)
- Hooks integration for Claude Code
- CLI: `cortex init`, `cortex mine`, `cortex search`, `cortex status`
- `BEST-PRACTICES.md` — guidance on filing memories so they're actually findable later (one topic per entry, lead with primary keywords, use wing/room deliberately, save the *why* not the *what*)

### Attribution
- This release is a fork of [MemPalace v3.1.0](https://github.com/milla-jovovich/mempalace) by milla-jovovich. See NOTICE for details.
