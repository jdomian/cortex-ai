"""
Example: mine a project directory into the cortex palace.

Run this against any directory of source code, markdown, or text files. cortex-ai
will scan, extract memorable content, classify it into wings/rooms, and store it
in the local palace at ~/.cortex/palace.

This is illustrative — replace SAMPLE_PROJECT_DIR with a real path on your machine.
"""

from pathlib import Path
from cortex.miner import mine, scan_project
from cortex.config import CortexConfig

# Pretend project directory — replace with your own.
SAMPLE_PROJECT_DIR = Path.home() / "Projects" / "my-app"


def main() -> None:
    cfg = CortexConfig()

    if not SAMPLE_PROJECT_DIR.exists():
        print(f"Sample project dir does not exist: {SAMPLE_PROJECT_DIR}")
        print("Edit this script to point at a real directory, then re-run.")
        return

    print(f"Scanning {SAMPLE_PROJECT_DIR} ...")
    file_count = scan_project(str(SAMPLE_PROJECT_DIR))
    print(f"Found {file_count} files to consider.")

    print("Mining into palace ...")
    mine(str(SAMPLE_PROJECT_DIR))
    print(f"Done. Palace at: {cfg.palace_path}")


if __name__ == "__main__":
    main()
