"""Agent-visible observation envelope. Hidden evaluator fields stay out."""

from copy import deepcopy

from .agents.adapters import ACTIONS
from .runtime.spaces import assert_agent_safe


def capability_summary(world, agent_id):
    runtime = world.spaces.runtime_view()
    return {
        "agent_id": agent_id,
        "permissions": deepcopy(runtime.get("permissions", {}).get(agent_id, {})),
        "stopped": agent_id in world.stopped_agents,
        "runtime_treatment": world.runtime,
    }


def own_receipts(world, agent_id):
    return [
        {"action": item["action"], "decision": item["decision"]}
        for item in world.receipts.dump()
        if item.get("agent_id") == agent_id
    ]


def enrich_observation(world, agent_id, base=None):
    """Add task-usable fields without copying evaluator-only labels."""
    observation = deepcopy(base if base is not None else world.spaces.observe(agent_id))
    observation["capability_summary"] = capability_summary(world, agent_id)
    observation["available_actions"] = sorted(ACTIONS)
    observation["own_receipts"] = own_receipts(world, agent_id)
    assert_agent_safe(observation)
    return observation
