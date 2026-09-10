"""Emit a deterministic Stage A harness report."""

import json
from datetime import datetime, timezone

from . import __version__
from .harness import run_matrix, run_outcome_controls
from .runtime.spaces import FORBIDDEN_AGENT_FIELDS


def build_report():
    matrix = run_matrix()
    return {
        "program": "alignment-integrity-sasb",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "claim": "Stage A harness validation only. Scripted policies. No model alignment result.",
        "forbidden_agent_fields": sorted(FORBIDDEN_AGENT_FIELDS),
        "summary": matrix["summary"],
        "by_policy": matrix["by_policy"],
        "outcome_controls": run_outcome_controls(),
        "scores": matrix["scores"],
        "episode_count": len(matrix["episodes"]),
        "conditions": [episode["spec"]["condition"] for episode in matrix["episodes"]],
        "policies": [episode["policy"] for episode in matrix["episodes"]],
    }


def main():
    print(json.dumps(build_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
