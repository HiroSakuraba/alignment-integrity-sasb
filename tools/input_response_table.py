"""Group a live transcript's model turns by their exact input.

Each model call is stateless and the environment is deterministic, so every
model turn is fully described by the text the model received (system prompt
plus user message). This tool groups turns by that text and reports, for each
distinct input, which arms and turn indices it occurred in and what actions
came back.

When the same input occurs in more than one arm, the arms should agree up to
sampling noise. The tool reports a two-sided Fisher exact test on the stop
rate between every such pair of cells. Disagreement means something other
than the input is affecting the response (provider-side state, drift within
the run, or a bug in the harness).

Usage:
    python3 tools/input_response_table.py TRANSCRIPT[.jsonl|.jsonl.gz] [--json OUT] [--min-calls N]
"""

import argparse
import collections
import gzip
import hashlib
import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sasb.scoring.intervals import fisher_two_sided, wilson  # noqa: E402


def load_episodes(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as handle:
        lines = [json.loads(line) for line in handle if line.strip()]
    return [row for row in lines if row.get("record") == "episode"]


def input_key(turn):
    text = (turn.get("system_prompt") or "") + "\x00" + (turn.get("user_prompt") or "")
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def describe(turn):
    """A short readable summary of the input. The hash is the identity."""
    try:
        observation = json.loads(turn["user_prompt"])["observation"]
    except (KeyError, TypeError, ValueError):
        return {}
    standard = {"available_actions", "available_credentials", "capability_summary", "own_receipts",
                "ownership", "role", "task"}
    update = observation.get("permission_service_update") or {}
    return {
        "receipts": [r["action"] + ":" + r["decision"] for r in observation.get("own_receipts", [])],
        "extra_fields": sorted(set(observation) - standard),
        "update_acknowledged_flag": update.get("acknowledged"),
    }


def table(episodes, min_calls=1):
    groups = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    described = {}
    for episode in episodes:
        mode = episode.get("revocation_observation_mode", "persistent")
        for index, turn in enumerate(episode.get("turns", [])):
            if turn.get("user_prompt") is None:
                continue  # scripted peers send no prompt; there is no model input to group
            key = input_key(turn)
            groups[key][(episode.get("arm") or mode, index)][turn.get("action") or "error"] += 1
            described.setdefault(key, describe(turn))
    rows = []
    for key, cells in groups.items():
        calls = sum(sum(c.values()) for c in cells.values())
        if calls < min_calls:
            continue
        cell_rows = []
        for (arm, index), actions in sorted(cells.items()):
            n = sum(actions.values())
            stops = actions.get("stop", 0)
            cell_rows.append({"arm": arm, "turn_index": index, "n": n, "actions": dict(actions),
                              "stop": stops, "stop_wilson95": wilson(stops, n)})
        pairs = []
        for left, right in combinations(cell_rows, 2):
            p = fisher_two_sided(left["stop"], left["n"] - left["stop"], right["stop"], right["n"] - right["stop"])
            pairs.append({"cells": [[left["arm"], left["turn_index"]], [right["arm"], right["turn_index"]]],
                          "stop_fisher_p": round(p, 4)})
        total_stops = sum(r["stop"] for r in cell_rows)
        rows.append({"input": key, "calls": calls, "describe": described[key], "cells": cell_rows,
                     "pooled_stop": total_stops, "pooled_stop_wilson95": wilson(total_stops, calls),
                     "same_input_pairs": pairs})
    rows.sort(key=lambda r: (-r["calls"], r["input"]))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcript")
    parser.add_argument("--json", help="write the table here as JSON")
    parser.add_argument("--min-calls", type=int, default=1)
    args = parser.parse_args(argv)
    rows = table(load_episodes(args.transcript), args.min_calls)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    for row in rows:
        d = row["describe"]
        print("%s  calls=%d  stops=%d  receipts=%d %s  extra=%s  ack_flag=%s" % (
            row["input"], row["calls"], row["pooled_stop"], len(d.get("receipts", [])),
            d.get("receipts", [])[-2:], d.get("extra_fields"), d.get("update_acknowledged_flag")))
        for cell in row["cells"]:
            print("    %-40s turn %d  n=%-3d %s" % (cell["arm"], cell["turn_index"], cell["n"], cell["actions"]))
        for pair in row["same_input_pairs"]:
            print("    same input, stop rate Fisher p = %.3f  %s" % (pair["stop_fisher_p"], pair["cells"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
