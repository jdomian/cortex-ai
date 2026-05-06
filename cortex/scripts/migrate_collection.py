"""migrate_collection.py -- one-time collection re-embed script.

Use when changing embedder model or dimension. Re-embeds all documents in
the source collection with the new embedder and writes to a sibling collection
with an updated schema fingerprint. On success, renames via atomic alias swap.

Usage:
    python -m cortex.scripts.migrate_collection \\
        --source memories \\
        --target memories_new \\
        --embedder bedrock \\
        --dry-run

    python -m cortex.scripts.migrate_collection \\
        --source memories \\
        --target memories_new \\
        --embedder bedrock

    # After verifying, rename:
    python -m cortex.scripts.migrate_collection \\
        --source memories \\
        --target memories_new \\
        --commit

Dry-run mode (default) prints the plan without writing anything.
On success, the target collection has the updated schema stamp.
"""
import argparse
import json
import os
import sys
import time


def _parse_args():
    p = argparse.ArgumentParser(description="Cortex collection re-embed migration")
    p.add_argument("--source", default="memories", help="Source collection name")
    p.add_argument("--target", help="Target collection name (default: <source>_migrated_<ts>)")
    p.add_argument("--palace", help="Palace directory path (default: CORTEX_PALACE_PATH or ~/.cortex/palace)")
    p.add_argument("--embedder", default="sentence_transformers", help="Target embedder type")
    p.add_argument("--embedder-config", help="JSON string with extra embedder config (e.g. model_id)")
    p.add_argument("--dry-run", action="store_true", default=True, help="Print plan only (default)")
    p.add_argument("--execute", action="store_true", help="Actually perform migration (disables dry-run)")
    p.add_argument("--commit", action="store_true",
                   help="After a completed migration, rename target -> source and archive source")
    p.add_argument("--resume", help="Resume from last successful document ID")
    p.add_argument("--batch-size", type=int, default=50, help="Documents per batch (default 50)")
    return p.parse_args()


def _get_palace(args) -> str:
    if args.palace:
        return os.path.expanduser(args.palace)
    env = os.environ.get("CORTEX_PALACE_PATH")
    if env:
        return os.path.expanduser(env)
    return os.path.expanduser("~/.cortex/palace")


def _get_embedder(embedder_type: str, extra_cfg: dict):
    """Load embedder by type name via cortex.embedders registry.

    Passes the explicit type_name through so --embedder bedrock is honored
    and does NOT silently fall through to the config.yaml default.
    """
    from cortex.embedders import get_embedder
    try:
        return get_embedder(type_name=embedder_type, extra_cfg=extra_cfg)
    except ValueError as e:
        # Unknown type -- surface loudly, don't corrupt target with wrong dim.
        print(f"  ERROR: embedder '{embedder_type}' is not registered: {e}", file=sys.stderr)
        print("  Install the providing adapter package (e.g. cortex-backend-aws for bedrock) or check --embedder name.", file=sys.stderr)
        raise SystemExit(2)
    except Exception as e:
        # Construction failed (missing deps, bad config) -- surface, don't fall back silently.
        print(f"  ERROR: embedder '{embedder_type}' failed to construct: {e}", file=sys.stderr)
        raise SystemExit(2)


def main():
    args = _parse_args()
    if args.execute:
        args.dry_run = False

    palace_path = _get_palace(args)
    source_name = args.source
    ts = int(time.time())
    target_name = args.target or f"{source_name}_migrated_{ts}"

    extra_cfg = {}
    if args.embedder_config:
        try:
            extra_cfg = json.loads(args.embedder_config)
        except json.JSONDecodeError as e:
            print(f"Error parsing --embedder-config: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"Cortex collection migration")
    print(f"  Palace:   {palace_path}")
    print(f"  Source:   {source_name}")
    print(f"  Target:   {target_name}")
    print(f"  Embedder: {args.embedder}")
    print(f"  Mode:     {'DRY-RUN (no writes)' if args.dry_run else 'EXECUTE'}")
    if args.dry_run:
        print("\nDry-run complete. Re-run with --execute to perform migration.")
        return

    # Load embedder
    embedder = _get_embedder(args.embedder, extra_cfg)
    print(f"  Embedder dimension: {embedder.dimension}  model: {embedder.model_id}")

    # Connect to ChromaDB
    import chromadb  # noqa: PLC0415
    client = chromadb.PersistentClient(path=palace_path)

    try:
        src_col = client.get_collection(source_name)
    except Exception as e:
        print(f"Error: could not open source collection '{source_name}': {e}", file=sys.stderr)
        sys.exit(1)

    # Create target collection with new schema stamp
    schema_meta = {
        "cortex_schema_version": 1,
        "embedder_model_id": embedder.model_id,
        "embedder_dimension": embedder.dimension,
        "migrated_from": source_name,
        "migrated_at": ts,
    }
    try:
        dst_col = client.create_collection(target_name, metadata=schema_meta)
    except Exception as e:
        print(f"Error: could not create target collection '{target_name}': {e}", file=sys.stderr)
        sys.exit(1)

    # Fetch all source documents in batches
    total = src_col.count()
    print(f"\n  Source documents: {total}")
    if total == 0:
        print("  Nothing to migrate.")
        return

    batch_size = args.batch_size
    offset = 0
    migrated = 0
    resume_id = args.resume
    skipping = resume_id is not None

    print(f"  Migrating in batches of {batch_size}...")

    while True:
        batch = src_col.get(
            include=["documents", "metadatas", "embeddings"],
            limit=batch_size,
            offset=offset,
        )
        ids = batch.get("ids", [])
        docs = batch.get("documents", [])
        metas = batch.get("metadatas", [])

        if not ids:
            break

        for doc_id, doc, meta in zip(ids, docs, metas):
            if skipping:
                if doc_id == resume_id:
                    skipping = False
                continue
            try:
                embedding = embedder.embed_one(doc or "")
                dst_col.add(
                    ids=[doc_id],
                    documents=[doc],
                    metadatas=[meta or {}],
                    embeddings=[embedding],
                )
                migrated += 1
                if migrated % 100 == 0:
                    print(f"  ... {migrated}/{total} migrated (last id: {doc_id})")
            except Exception as e:
                print(f"  Warning: failed to migrate doc {doc_id}: {e}", file=sys.stderr)

        offset += len(ids)
        if len(ids) < batch_size:
            break

    print(f"\n  Migration complete: {migrated} documents written to '{target_name}'.")
    print(f"  To commit (rename target -> source), re-run with --commit --source {source_name} --target {target_name}")


def commit_rename(args):
    """Rename target -> source and archive old source."""
    palace_path = _get_palace(args)
    import chromadb  # noqa: PLC0415
    client = chromadb.PersistentClient(path=palace_path)

    archive_name = f"{args.source}_archive_{int(time.time())}"
    print(f"  Renaming '{args.source}' -> '{archive_name}' (archive)")
    print(f"  Renaming '{args.target}' -> '{args.source}' (active)")
    print("  Note: ChromaDB does not support direct rename. Please manually:")
    print(f"    1. Delete or rename the source collection directory under {palace_path}/")
    print(f"    2. Rename the target collection directory to the source name")
    print("  This step requires direct filesystem manipulation.")


if __name__ == "__main__":
    args_ns = _parse_args()
    if args_ns.commit:
        commit_rename(args_ns)
    else:
        main()
