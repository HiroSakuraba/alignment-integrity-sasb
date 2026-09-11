#!/usr/bin/env python3
"""Regenerate the harness report and compare the stable fields."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sasb.__main__ import build_report  # noqa: E402
from sasb.artifacts import build_artifact_report  # noqa: E402
from sasb.chain import build_chain_report  # noqa: E402
from sasb.landscape import build_landscape
from sasb.controls import build_controls_report  # noqa: E402


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
    chain_path = ROOT / "reports" / "chain-run.json"
    if json.loads(chain_path.read_text()) != build_chain_report():
        sys.stderr.write("reports/chain-run.json is stale; run make report\n")
        sys.exit(1)
    controls_path = ROOT / "reports" / "stage-a-controls.json"
    if json.loads(controls_path.read_text()) != build_controls_report():
        sys.stderr.write("reports/stage-a-controls.json is stale; run make report\n")
        sys.exit(1)
    artifact_path = ROOT / "reports" / "artifact-run.json"
    if json.loads(artifact_path.read_text()) != build_artifact_report():
        sys.stderr.write("reports/artifact-run.json is stale; run make report\n")
        sys.exit(1)
    if json.loads((ROOT / "reports/perturbation-map.json").read_text()) != build_landscape():
        sys.exit("reports/perturbation-map.json is stale; run make report")
    print("perturbation map, maintenance, chain, Stage A control, and artifact reports match generated fixtures")


if __name__ == "__main__":
    main()
