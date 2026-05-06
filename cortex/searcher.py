#!/usr/bin/env python3
"""
searcher.py — Find anything. Exact words.

Semantic search against the palace.
Returns verbatim text -- the actual words, never summaries.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional


logger = logging.getLogger("cortex_mcp")


def _age_band(age_days: float) -> str:
    """Classify result age into a display band."""
    if age_days < 1:
        return "fresh"
    if age_days <= 7:
        return "recent"
    if age_days <= 90:
        return "old"
    return "ancient"


def _compute_age(meta: dict, source_file: str) -> tuple:
    """Return (age_days, age_band) for a search result.

    Priority: metadata last_accessed epoch > source_file mtime > 0 (unknown).
    Score is display-only; decay.py remains the sole source of decay math.
    """
    now = time.time()

    last_accessed = meta.get("last_accessed")
    if last_accessed:
        try:
            age_days = (now - float(last_accessed)) / 86400
            return round(age_days, 1), _age_band(age_days)
        except (TypeError, ValueError):
            pass

    if source_file and source_file != "?":
        try:
            mtime = os.path.getmtime(source_file)
            age_days = (now - mtime) / 86400
            return round(age_days, 1), _age_band(age_days)
        except OSError:
            pass

    return None, "unknown"


class SearchError(Exception):
    """Raised when search cannot proceed (e.g. no palace found)."""


def _resolve_collection_for_read(client, config=None):
    """Resolve ChromaDB collection name for read operations.

    Tries the configured/env-var name first, then falls back to the legacy
    'mempalace_drawers' name. Read-only safe -- never creates collections.

    Raises RuntimeError if no collection is found under either name.
    """
    from .config import CortexConfig
    if config is None:
        config = CortexConfig()
    primary = config.collection_name
    try:
        client.get_collection(primary)
        return primary
    except Exception:
        pass
    legacy = "mempalace_drawers"
    if primary != legacy:
        try:
            client.get_collection(legacy)
            logger.warning(
                "Collection %r not found; using legacy %r. "
                "Set CORTEX_COLLECTION_NAME=%s to suppress this warning.",
                primary, legacy, legacy,
            )
            return legacy
        except Exception:
            pass
    raise RuntimeError(
        f"No collection found (tried {primary!r} and {legacy!r}). "
        "Run: cortex init && cortex mine"
    )


def resolve_collection_name_for_write(client, config=None):
    """Resolve ChromaDB collection name for write operations.

    Unlike reads, write resolution raises on ambiguity to prevent split-brain
    between 'cortex_drawers' and 'mempalace_drawers'. When CORTEX_COLLECTION_NAME
    is explicitly set, that value is trusted unconditionally.

    Raises ValueError if the default 'cortex_drawers' would be auto-created
    while a 'mempalace_drawers' collection already exists.
    """
    from .config import CortexConfig, DEFAULT_COLLECTION_NAME
    if config is None:
        config = CortexConfig()
    primary = config.collection_name
    if os.environ.get("CORTEX_COLLECTION_NAME"):
        return primary
    if primary == DEFAULT_COLLECTION_NAME:
        try:
            client.get_collection("mempalace_drawers")
            raise ValueError(
                "Refusing to auto-create 'cortex_drawers' while a 'mempalace_drawers' "
                "collection exists. Set CORTEX_COLLECTION_NAME=mempalace_drawers explicitly."
            )
        except ValueError:
            raise
        except Exception:
            pass
    return primary


def search(query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5):
    """
    Search the palace. Returns verbatim drawer content.
    Optionally filter by wing (project) or room (aspect).
    """
    try:
        import chromadb  # lazy -- avoids module-level Lambda cold-start cost
        client = chromadb.PersistentClient(path=palace_path)
        col_name = _resolve_collection_for_read(client)
        col = client.get_collection(col_name)
    except RuntimeError as e:
        print(f"\n  No palace found at {palace_path}")
        print("  Run: cortex init <dir> then cortex mine <dir>")
        raise SearchError(str(e))
    except Exception:
        print(f"\n  No palace found at {palace_path}")
        print("  Run: cortex init <dir> then cortex mine <dir>")
        raise SearchError(f"No palace found at {palace_path}")

    # Build where filter
    where = {}
    if wing and room:
        where = {"$and": [{"wing": wing}, {"room": room}]}
    elif wing:
        where = {"wing": wing}
    elif room:
        where = {"room": room}

    try:
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)

    except Exception as e:
        print(f"\n  Search error: {e}")
        raise SearchError(f"Search error: {e}") from e

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    if not docs:
        print(f'\n  No results found for: "{query}"')
        return

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if wing:
        print(f"  Wing: {wing}")
    if room:
        print(f"  Room: {room}")
    print(f"{'=' * 60}\n")

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
        similarity = round(1 - dist, 3)
        source = Path(meta.get("source_file", "?")).name
        wing_name = meta.get("wing", "?")
        room_name = meta.get("room", "?")

        print(f"  [{i}] {wing_name} / {room_name}")
        print(f"      Source: {source}")
        print(f"      Match:  {similarity}")
        print()
        # Print the verbatim text, indented
        for line in doc.strip().split("\n"):
            print(f"      {line}")
        print()
        print(f"  {'─' * 56}")

    print()


def search_memories(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    current_session_id: Optional[str] = None,
    exclude_current_session: bool = False,
) -> dict:
    """Programmatic search -- returns a dict instead of printing.

    Used by the MCP server and other callers that need data.

    Args:
        query: search query string
        palace_path: path to the ChromaDB palace directory
        wing: optional wing filter
        room: optional room filter
        n_results: max results to return (applied after session filter)
        current_session_id: session UUID; combined with exclude_current_session
        exclude_current_session: when True, post-filter results whose session_id
            matches current_session_id. Applied after ranking, before truncation.
    """
    try:
        import chromadb  # lazy -- avoids module-level Lambda cold-start cost
        client = chromadb.PersistentClient(path=palace_path)
        col_name = _resolve_collection_for_read(client)
        col = client.get_collection(col_name)
    except Exception as e:
        logger.error("No palace found at %s: %s", palace_path, e)
        return {
            "error": "No palace found",
            "hint": "Run: cortex init <dir> && cortex mine <dir>",
        }

    # Build where filter
    where = {}
    if wing and room:
        where = {"$and": [{"wing": wing}, {"room": room}]}
    elif wing:
        where = {"wing": wing}
    elif room:
        where = {"room": room}

    # Request more results when session filter is active so n_results is
    # honoured after filtering. Cap at a reasonable upper bound.
    fetch_n = n_results
    if exclude_current_session and current_session_id:
        fetch_n = min(n_results * 4, 50)

    try:
        kwargs = {
            "query_texts": [query],
            "n_results": fetch_n,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)
    except Exception as e:
        return {"error": f"Search error: {e}"}

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    hits = []
    for doc, meta, dist in zip(docs, metas, dists):
        source_full = meta.get("source_file", "?")
        age_days, band = _compute_age(meta, source_full)
        hits.append(
            {
                "text": doc,
                "wing": meta.get("wing", "unknown"),
                "room": meta.get("room", "unknown"),
                "source_file": Path(source_full).name,
                "similarity": round(1 - dist, 3),
                "age_days": age_days,
                "age_band": band,
                "session_id": meta.get("session_id"),
            }
        )

    # Session exclusion filter (post-rank)
    if exclude_current_session and current_session_id:
        hits = [h for h in hits if h.get("session_id") != current_session_id]

    # Trim to requested count
    hits = hits[:n_results]

    return {
        "query": query,
        "filters": {"wing": wing, "room": room},
        "results": hits,
    }
