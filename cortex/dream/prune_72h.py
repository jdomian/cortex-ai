"""Dream step: prune STM 72h log. Thin wrapper over cortex.stm.prune."""
from cortex.stm import STM


def run(path: str = None, window_hours: int = 72, stm=None) -> dict:
    """Prune expired events from the STM log.

    v0.5.0 kwargs path and window_hours preserved for back-compat.
    New in v0.6.0: optional `stm` backend. When provided, path is ignored.
    """
    if stm is not None:
        result = stm.prune(older_than_hours=window_hours)
        return {"step": "prune_72h", **result}
    stm_instance = STM(path=path, window_hours=window_hours)
    result = stm_instance.prune()
    return {"step": "prune_72h", **result}
