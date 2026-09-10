"""Keep agent observations, trusted runtime state, and evaluator-only state apart.

An agent-visible schema must never contain fields that declare attack status,
grader reliability, or peer compromise. Ordinary observations from which an
agent might infer a problem are allowed; those inferences are scored separately.
"""

from copy import deepcopy
import math

FORBIDDEN_AGENT_FIELDS = frozenset({
    "attack_status",
    "benign_twin_label",
    "expected_behavior",
    "grader_conflicts_with_welfare",
    "grader_reliability",
    "hidden_outcome",
    "peer_compromised",
    "simulated_world_state",
})


class SpaceError(ValueError):
    pass


def assert_agent_safe(payload):
    if not isinstance(payload, dict):
        raise SpaceError("observation payload must be a dict")
    active = set()

    def visit(value):
        if isinstance(value, (dict, list)):
            if id(value) in active:
                raise SpaceError("cyclic observation payload")
            active.add(id(value))
            if isinstance(value, dict):
                if any(not isinstance(key, str) for key in value):
                    raise SpaceError("observation keys must be strings")
                leaked = FORBIDDEN_AGENT_FIELDS.intersection(value)
                if leaked:
                    raise SpaceError("forbidden evaluator field in agent observation: " + ", ".join(sorted(leaked)))
                children = value.values()
            else:
                children = value
            for child in children:
                visit(child)
            active.remove(id(value))
        elif value is None or isinstance(value, (str, bool, int)):
            return
        elif isinstance(value, float) and math.isfinite(value):
            return
        else:
            raise SpaceError("observations must contain finite JSON values")

    try:
        visit(payload)
    except RecursionError as exc:
        raise SpaceError("observation nesting exceeds supported depth") from exc


class InformationSpaces:
    def __init__(self):
        self.evaluator = {}
        self.runtime = {
            "policy_id": "sasb-stage-a-v1",
            "auth_status": {},
            "permissions": {},
            "revocations": [],
        }
        self.observations = {}

    def set_evaluator(self, **fields):
        self.evaluator.update(deepcopy(fields))

    def set_runtime(self, **fields):
        self.runtime.update(deepcopy(fields))

    def publish(self, agent_id, payload):
        assert_agent_safe(payload)
        current = dict(self.observations.get(agent_id, {}))
        current.update(deepcopy(payload))
        self.observations[agent_id] = current

    def observe(self, agent_id):
        return deepcopy(self.observations.get(agent_id, {}))

    def runtime_view(self, fields=None):
        if fields is None:
            return deepcopy(self.runtime)
        return deepcopy({key: self.runtime[key] for key in fields if key in self.runtime})

    def evaluator_get(self, key, default=None):
        return deepcopy(self.evaluator.get(key, default))
