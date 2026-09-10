#!/usr/bin/env python3
"""Regenerate the harness report and compare the stable fields."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sasb.__main__ import build_report  # noqa: E402


def stable(report):
    return {
        "program": report["program"],
        "version": report["version"],
        "claim": report["claim"],
        "forbidden_agent_fields": report["forbidden_agent_fields"],
        "summary": report["summary"],
        "by_policy": report["by_policy"],
        "outcome_controls": report["outcome_controls"],
        "scores": report["scores"],
        "episode_count": report["episode_count"],
        "conditions": report["conditions"],
        "policies": report["policies"],
    }


def main():
    generated = build_report()
    if not all(control["passed"] for control in generated["outcome_controls"]):
        sys.stderr.write("outcome checker failed its bypass controls\n")
        sys.exit(1)
    path = ROOT / "reports" / "harness-run.json"
    recorded = json.loads(path.read_text())
    if stable(generated) != stable(recorded):
        sys.stderr.write("reports/harness-run.json is stale; run python3 -m sasb > reports/harness-run.json\n")
        sys.exit(1)
    print("harness report matches generated Stage A matrix")


if __name__ == "__main__":
    main()
