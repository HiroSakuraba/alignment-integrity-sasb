"""Additional Stage A engineering reports. Scripted only."""

import json

from .chain import build_chain_report
from .harness import run_anchors, run_runtime_contrast
from .scoring.persistence import summarize_chain


def build_controls_report():
    chain = build_chain_report()
    persistence = summarize_chain(chain["cases"])
    anchors = run_anchors()
    return {
        "claim": "Stage A engineering controls. No model, no training result.",
        "anchors": {
            "summary": anchors["summary"],
            "scores": anchors["scores"],
        },
        "runtime_contrast": run_runtime_contrast(),
        "persistence": persistence["summary"],
        "persistence_rows": persistence["rows"],
    }


def main():
    print(json.dumps(build_controls_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
