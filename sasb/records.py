"""Minimal episode identity fields from framework \u00a77.1, without model calls."""

import hashlib
import json
from pathlib import Path

from . import __version__

ROOT = Path(__file__).resolve().parents[1]


def _hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_hashes():
    prompt_dir = ROOT / "prompts"
    files = sorted(path for path in prompt_dir.glob("*") if path.is_file())
    return {path.name: _hash_file(path) for path in files}


def usage_total(episode):
    receipts = episode.get("receipts", [])
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "retries": 0,
        "recorded_actions": len(receipts),
        "note": "scripted actors declare no live-model usage",
    }


def episode_record(world, episode, provider=None):
    spec = episode["spec"]
    record = {
        "program": "alignment-integrity-sasb",
        "version": __version__,
        "scenario_id": spec["scenario_id"],
        "condition": spec["condition"],
        "policy": episode.get("policy"),
        "runtime_treatment": world.runtime,
        "mode": episode.get("mode", "swarm"),
        "environment": spec.get("environment"),
        "prompt_hashes": prompt_hashes(),
        "usage": usage_total(episode),
        "network": False,
        "provider": None,
        "model": None,
        "claim": "Stage A identity record only. No model checkpoint or decoding settings.",
    }
    if provider:
        from .agents.providers import provider_identity
        identity = provider_identity(provider)
        record["provider"] = identity["provider"]
        record["model"] = identity["model"]
        record["network"] = identity["network"]
        record["claim"] = "Identity record with pinned provider metadata. Key values are not stored."
    return record


def dump_record(record):
    return json.dumps(record, sort_keys=True, indent=2)
