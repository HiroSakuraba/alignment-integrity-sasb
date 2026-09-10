"""Authenticated identities and roles. The runtime, not the model, assigns these."""

ROLES = ("planner", "worker", "reviewer", "coordinator")


class IdentityError(ValueError):
    pass


class Roster:
    def __init__(self, agents):
        self.agents = {}
        for agent in agents:
            if agent["role"] not in ROLES:
                raise IdentityError("unknown role: " + agent["role"])
            self.agents[agent["agent_id"]] = dict(agent)

    def get(self, agent_id):
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise IdentityError("unknown agent") from exc

    def by_role(self, role):
        matches = [item for item in self.agents.values() if item["role"] == role]
        if not matches:
            raise IdentityError("no agent with role " + role)
        return matches[0]
