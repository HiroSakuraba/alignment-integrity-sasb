"""Four-role episode runner. Scripted results do not measure model alignment."""

from .executor import Executor, completed_violation
from .policies import actors_for
from .scenarios.maintenance import CONDITIONS, specification
from .scoring.scorecard import score_episode, summarize
from .world import World

TURN_ORDER = ("coordinator-1", "planner-1", "worker-1", "reviewer-1")


def run_episode(condition, policy="compliant"):
    spec = specification(condition)
    world = World(spec)
    actors = actors_for(condition, policy)
    executor = Executor(world)
    for agent_id in TURN_ORDER:
        observation = world.spaces.observe(agent_id)
        decision = actors[agent_id].decide(observation)
        executor.apply(agent_id, decision.action, decision.arguments)
        if agent_id == "worker-1":
            while actors[agent_id].index < len(actors[agent_id].steps):
                observation = world.spaces.observe(agent_id)
                decision = actors[agent_id].decide(observation)
                executor.apply(agent_id, decision.action, decision.arguments)
    episode = {
        "spec": spec,
        "policy": policy,
        "receipts": world.receipts.dump(),
        "reports": world.reports.delivered(),
        "writes": list(world.resources.writes),
        "workspace_files": list(world.workspace.files),
        "completed_violation": completed_violation(world),
        "evaluator_keys": sorted(world.spaces.evaluator),
        "agent_observation_keys": sorted({
            key
            for agent_id in world.roster.agents
            for key in world.spaces.observe(agent_id)
        }),
    }
    episode["score"] = score_episode(episode)
    return episode


def run_matrix(conditions=CONDITIONS):
    rows = []
    episodes = []
    for condition in conditions:
        for policy in ("compliant", "noncompliant"):
            episode = run_episode(condition, policy)
            episodes.append(episode)
            rows.append(episode["score"])
    return {"episodes": episodes, "scores": rows, "summary": summarize(rows)}
