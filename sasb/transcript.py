"""Committed run transcripts and free replay for the Stage B driver.

One JSONL file per run under reports/transcripts/. The first record is a run
header: schema, pinned model, provider, runtime treatment, mode, conditions,
model roles, cap, source commit and the sha256 of every prompt file. Each later
record is one episode, carrying every agent turn's full observation, raw model
text, parsed action and arguments, usage and error status, alongside the
receipts and score the episode produced.

A committed transcript replays without an API key:

    python3 -m sasb.live --replay reports/transcripts/<file>.jsonl

The recorded responses are fed back through the same harness, executor and
scorer, so a reader can confirm the published numbers or change the runtime
treatment, scoring rule or monitor and see exactly what moves, at no cost.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .agents.adapters import AdapterError, Decision, Usage

SCHEMA = "sasb-transcript-v1"
ROOT = Path(__file__).resolve().parents[1]


def source_commit():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=5, cwd=str(ROOT))
        return out.stdout.strip() or None
    except Exception:
        return None


def prompt_digests():
    prompt_dir = ROOT / "prompts"
    if not prompt_dir.exists():
        return {}
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(prompt_dir.glob("*")) if p.is_file()}


def run_id(model, runtime, mode):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = hashlib.sha256(("%s|%s|%s" % (model, runtime, mode)).encode()).hexdigest()[:8]
    return "%s-%s-%s" % (stamp, (model or "local").replace(".", "-"), tag)


def default_path(model, runtime, mode, root="reports/transcripts"):
    return str(Path(root) / (run_id(model, runtime, mode) + ".jsonl"))


def cell_key(condition, role, runtime, mode):
    return "|".join([str(condition), str(role), str(runtime), str(mode)])


def write_header(path, **fields):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "record": "run_header",
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_commit": source_commit(),
        "prompt_sha256": prompt_digests(),
        **fields,
    }
    with dest.open("w") as fh:
        fh.write(json.dumps(header, sort_keys=True, default=str) + "\n")
    return header


def append_episode(path, header, episode):
    """One line per episode: every turn, plus the receipts and score it produced."""
    if not path:
        return None
    turns = [
        {"agent_id": row.get("agent_id"), "observation": row.get("observation"),
         "raw_response": row.get("raw"), "action": row.get("action"),
         "arguments": row.get("arguments"), "usage": row.get("usage"),
         "error": row.get("error")}
        for row in episode.get("trace", [])
    ]
    record = dict(header, record="episode", turns=turns,
                  receipts=episode.get("receipts", []),
                  score=episode.get("score", {}),
                  usage=episode.get("usage", {}))
    record["turns_digest"] = hashlib.sha256(
        json.dumps(turns, sort_keys=True, default=str).encode()).hexdigest()[:16]
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return str(dest)


def load(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if not rows or rows[0].get("record") != "run_header":
        raise ValueError("transcript is missing its run header")
    return rows[0], [r for r in rows[1:] if r.get("record") == "episode"]


class ReplayIndex:
    """Recorded turns keyed by cell and agent, so a replay needs no network."""

    def __init__(self, path):
        self.header, episodes = load(path)
        self.cells = {}
        for ep in episodes:
            key = cell_key(ep.get("condition"), ep.get("role"), ep.get("runtime"), ep.get("mode"))
            per_agent = self.cells.setdefault(key, {})
            for turn in ep["turns"]:
                per_agent.setdefault(turn["agent_id"], []).append(turn)

    def has(self, condition, role, runtime, mode):
        return cell_key(condition, role, runtime, mode) in self.cells

    def actors(self, condition, role, runtime, mode):
        per_agent = self.cells.get(cell_key(condition, role, runtime, mode), {})
        return {agent: ReplayActor(turns) for agent, turns in per_agent.items()}


class ReplayActor:
    """Replays recorded turns in order. Usage is zero: nothing is bought."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.index = 0
        self.last_usage = Usage(0, 0, 0)
        self.last_reported_model = "replay"

    @property
    def steps(self):
        # _more_worker_turns uses this to stop at the recorded turn count.
        return self.turns

    def decide(self, observation):
        if self.index >= len(self.turns):
            raise AdapterError("replay exhausted at turn %d" % self.index)
        turn = self.turns[self.index]
        self.index += 1
        if turn.get("error") or turn.get("raw_response") is None:
            raise AdapterError(turn.get("error") or "recorded response was unparseable")
        return Decision(turn["action"], turn["arguments"], turn["raw_response"], Usage(0, 0, 0))
