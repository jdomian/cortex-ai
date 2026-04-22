"""
Example: semantic search against the cortex palace.

Run this after you've populated your palace with `cortex init` + `cortex mine`.
"""

from cortex.searcher import search_memories


def main() -> None:
    query = "how did we handle user authentication?"
    print(f"Query: {query}")
    print()

    results = search_memories(query=query, limit=5)

    if not results:
        print("No matches. Try `cortex mine /path/to/your/project` first.")
        return

    for i, hit in enumerate(results, 1):
        print(f"--- Match {i} (score={hit.get('score', 0):.3f}) ---")
        print(hit.get("content", "")[:300])
        print()


if __name__ == "__main__":
    main()
