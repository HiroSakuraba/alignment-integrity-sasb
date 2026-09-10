"""Keep agent observations, trusted runtime state, and evaluator-only state apart.

An agent-visible schema must never contain fields that declare attack status,
grader reliability, or peer compromise. Ordinary observations from which an
agent might infer a problem are allowed; those inferences are scored separately.
"""

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
    leaked = FORBIDDEN_AGENT_FIELDS.intersection(payload)
    if leaked:
        raise SpaceError("forbidden evaluator field in agent observation: " + ", ".join(sorted(leaked)))
    for value in payload.values():
        if isinstance(value, dict):
            assert_agent_safe(value)


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
        self.evaluator.update(fields)

    def set_runtime(self, **fields):
        self.runtime.update(fields)

    def publish(self, agent_id, payload):
        assert_agent_safe(payload)
        current = dict(self.observations.get(agent_id, {}))
        current.update(payload)
        self.observations[agent_id] = current

    def observe(self, agent_id):
        return dict(self.observations.get(agent_id, {}))

    def runtime_view(self, fields=None):
        if fields is None:
            return dict(self.runtime)
        return {key: self.runtime[key] for key in fields if key in self.runtime}

    def evaluator_get(self, key, default=None):
        return self.evaluator.get(key, default)
