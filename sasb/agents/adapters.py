"""JSON action contract shared by scripted policies and future model adapters."""

import json
from dataclasses import dataclass

ACTIONS = frozenset({
    "inspect_resource",
    "complete_maintenance",
    "use_credential",
    "report",
    "accept_update",
    "reject_update",
    "stop",
    "message_peer",
    "noop",
})


class AdapterError(ValueError):
    pass


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0


@dataclass(frozen=True)
class Decision:
    action: str
    arguments: dict
    raw: str
    usage: Usage


def parse_decision(raw):
    try:
        item = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AdapterError("invalid JSON action") from exc
    if "action" not in item or item["action"] not in ACTIONS:
        raise AdapterError("invalid action schema")
    arguments = item.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise AdapterError("arguments must be an object")
    return item["action"], arguments


class ScriptedActor:
    def __init__(self, steps, input_tokens=0, output_tokens=16):
        self.steps = tuple(steps)
        self.index = 0
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def decide(self, observation):
        if self.index >= len(self.steps):
            action, arguments = "noop", {}
        else:
            action, arguments = self.steps[self.index]
            self.index += 1
        raw = json.dumps({"action": action, "arguments": arguments}, separators=(",", ":"))
        parsed_action, parsed_arguments = parse_decision(raw)
        return Decision(parsed_action, parsed_arguments, raw, Usage(self.input_tokens, self.output_tokens))
