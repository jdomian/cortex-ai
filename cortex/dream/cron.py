"""Dream cron installer. Manages the nightly maintenance cron entry."""
import os
import subprocess
import sys
from typing import Optional


def install_cron(schedule: str = "0 3 * * *", command: str = None,
                 python_path: str = None) -> str:
    """Install or replace the cortex dream cron entry. Returns the crontab line added."""
    if python_path is None:
        python_path = sys.executable
    if command is None:
        command = f"{python_path} -m cortex dream run"

    cron_line = f"{schedule} {command} >> /tmp/cortex-dream.log 2>&1"
    marker = "# cortex-dream-nightly"
    full_line = f"{cron_line}  {marker}"

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
    except Exception:
        existing = ""

    lines = [line for line in existing.splitlines() if marker not in line]
    lines.append(full_line)
    new_crontab = "\n".join(lines) + "\n"

    proc = subprocess.run(["crontab", "-"], input=new_crontab, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"crontab install failed: {proc.stderr}")
    return full_line


def remove_cron() -> bool:
    """Remove the cortex dream cron entry."""
    marker = "# cortex-dream-nightly"
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
    except Exception:
        return False

    lines = [line for line in existing.splitlines() if marker not in line]
    new_crontab = "\n".join(lines) + "\n"
    proc = subprocess.run(["crontab", "-"], input=new_crontab, capture_output=True, text=True)
    return proc.returncode == 0
