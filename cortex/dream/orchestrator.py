"""Dream orchestrator -- runs all cross-cutting maintenance sweeps in order."""
import os
from typing import Dict

from . import prune_72h, consolidate, decay, patterns as _patterns_mod


class Dream:
    def __init__(self, config_path=None, vector_backend=None,
                 stm_backend=None, kv_backend=None):
        self.config_path = config_path or os.path.expanduser("~/.cortex/config.yaml")
        self._vector = vector_backend
        self._stm = stm_backend
        self._kv = kv_backend

    def _run_step(self, step_name: str) -> Dict:
        if step_name == "prune_72h":
            kwargs = {}
            if self._stm is not None:
                kwargs["stm"] = self._stm
            return prune_72h.run(**kwargs)
        elif step_name == "consolidate":
            kwargs = {}
            if self._vector is not None:
                kwargs["vector"] = self._vector
            return consolidate.run(**kwargs)
        elif step_name == "decay":
            kwargs = {}
            if self._vector is not None:
                kwargs["vector"] = self._vector
            return decay.run(**kwargs)
        elif step_name == "patterns":
            kwargs = {}
            if self._vector is not None:
                kwargs["vector"] = self._vector
            if self._kv is not None:
                kwargs["kv"] = self._kv
            return _patterns_mod.run(**kwargs)
        else:
            return {"error": f"unknown step: {step_name}"}

    def run(self) -> Dict:
        results = {}
        for step in ["prune_72h", "consolidate", "decay", "patterns"]:
            try:
                results[step] = self._run_step(step)
            except Exception as e:
                results[step] = {"error": str(e)}
        return results


def run_nightly() -> Dict:
    return Dream().run()
