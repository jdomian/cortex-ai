"""Dream step: prune STM 72h log. Thin wrapper over cortex.stm.prune."""
from cortex.stm import STM


def run(path: str = None, window_hours: int = 72) -> dict:
    stm = STM(path=path, window_hours=window_hours)
    result = stm.prune()
    return {"step": "prune_72h", **result}
