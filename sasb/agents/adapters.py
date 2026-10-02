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


def argument_contract():
    """Per-action argument names, generated from ARGUMENTS (the parser's table).

    ``name?`` is optional. ``{}`` means the action takes no arguments.
    """
    parts = []
    for action in sorted(ARGUMENTS):
        required, allowed = ARGUMENTS[action]
        names = [n for n in sorted(allowed) if n in required] + [n + "?" for n in sorted(allowed - required)]
        parts.append("%s {%s}" % (action, ", ".join(names)))
    return "; ".join(parts)


def validate_action(action, arguments):
    if not isinstance(action, str) or action not in ACTIONS:
        raise AdapterError("invalid action schema: unknown action %r" % (action,))
    if not isinstance(arguments, dict):
        raise AdapterError("arguments must be an object, got %s" % type(arguments).__name__)
    required, allowed = ARGUMENTS[action]
    missing = sorted(required - set(arguments))
    unexpected = sorted(set(arguments) - allowed)
    if missing or unexpected:
        raise AdapterError(
            "missing or unexpected action arguments for %s: missing=%s unexpected=%s allowed=%s"
            % (action, missing, unexpected, sorted(allowed))
        )
    bad = sorted(key for key, value in arguments.items() if not isinstance(value, str) or not value.strip())
    if bad:
        raise AdapterError("action arguments must be nonempty strings: %s" % bad)
    return action, dict(arguments)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AdapterError("duplicate JSON field %r" % (key,))
        result[key] = value
    return result


def _reject_constant(value):
    raise AdapterError("non-finite JSON value")


def parse_decision(raw):
    if not isinstance(raw, str):
        raise AdapterError("action output must be text")
    try:
        item = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise AdapterError("invalid JSON action: %s" % exc.msg) from exc
    except RecursionError as exc:
        raise AdapterError("invalid JSON action: nesting too deep") from exc
    if not isinstance(item, dict):
        raise AdapterError("invalid action schema: top level is %s, not an object" % type(item).__name__)
    if "action" not in item:
        raise AdapterError("invalid action schema: missing 'action'")
    extra = sorted(set(item) - {"action", "arguments"})
    if extra:
        raise AdapterError("invalid action schema: unexpected top-level fields %s" % extra)
    arguments = item.get("arguments", {})
    if arguments is None:
        # "arguments": null is the same as {} for actions that take none;
        # actions with required arguments still fail validation below.
        arguments = {}
    return validate_action(item["action"], arguments)


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
