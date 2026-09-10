"""Frozen peer-message payloads for later replay. No model search."""

import json
from pathlib import Path

from .grammar import FAMILIES

REPLAY_DIR = Path(__file__).resolve().parent / "replay"


def list_replays():
    return tuple(sorted(path.stem for path in REPLAY_DIR.glob("*.json")))


def load_replay(name):
    path = REPLAY_DIR / (name + ".json")
    payload = json.loads(path.read_text())
    if payload.get("family") not in FAMILIES:
        raise ValueError("replay family is not in the Stage A grammar")
    if not isinstance(payload.get("text"), str) or not payload["text"].strip():
        raise ValueError("replay text must be a nonempty string")
    return payload


def apply_replay(world, agent_id, name):
    """Present a frozen message as attributed peer content, not as a permission."""
    payload = load_replay(name)
    observation = world.spaces.observe(agent_id)
    messages = list(observation.get("peer_messages", []))
    event = world.events.append("replay", "frozen-replay", {"replay_id": payload["id"]})
    messages.append({
        "source_id": payload.get("source_id", "frozen-replay"),
        "text": payload["text"],
        "event_id": event["event_id"],
        "replay_id": payload["id"],
        "authority": "attributed_content",
    })
    world.spaces.publish(agent_id, {"peer_messages": messages})
    return payload
