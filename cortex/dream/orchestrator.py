"""Dream orchestrator -- runs all cross-cutting maintenance sweeps in order."""
import os
from typing import Dict

from . import prune_72h, consolidate, decay, patterns as _patterns_mod


class Dream:
    def __init__(self, config_path=None):
        self.config_path = config_path or os.path.expanduser("~/.cortex/config.yaml")

    def _run_step(self, step_name: str) -> Dict:
        if step_name == "prune_72h":
            return prune_72h.run()
        elif step_name == "consolidate":
            return consolidate.run()
        elif step_name == "decay":
            return decay.run()
        elif step_name == "patterns":
            return _patterns_mod.run()
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
