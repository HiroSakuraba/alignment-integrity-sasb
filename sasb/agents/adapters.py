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
    "remember_message",
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


ARGUMENTS = {
    "inspect_resource": (set(), {"tenant"}),
    "complete_maintenance": (set(), {"resource"}),
    "use_credential": ({"credential", "resource"}, {"credential", "resource"}),
    "report": ({"risk", "evidence"}, {"risk", "evidence"}),
    "accept_update": ({"kind"}, {"kind"}),
    "reject_update": ({"reason"}, {"reason"}),
    "stop": ({"reason"}, {"reason"}),
    "message_peer": ({"to", "text"}, {"to", "text"}),
    "noop": (set(), set()),
    "remember_message": ({"event_id"}, {"event_id"}),
}


def validate_action(action, arguments):
    if not isinstance(action, str) or action not in ACTIONS:
        raise AdapterError("invalid action schema")
    if not isinstance(arguments, dict):
        raise AdapterError("arguments must be an object")
    required, allowed = ARGUMENTS[action]
    if not required.issubset(arguments) or set(arguments) - allowed:
        raise AdapterError("missing or unexpected action arguments")
    if any(not isinstance(value, str) or not value.strip() for value in arguments.values()):
        raise AdapterError("action arguments must be nonempty strings")
    return action, dict(arguments)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AdapterError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise AdapterError("non-finite JSON value")


def parse_decision(raw):
    if not isinstance(raw, str):
        raise AdapterError("action output must be text")
    try:
        item = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise AdapterError("invalid JSON action") from exc
    if not isinstance(item, dict) or "action" not in item or set(item) - {"action", "arguments"}:
        raise AdapterError("invalid action schema")
    return validate_action(item["action"], item.get("arguments", {}))


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
