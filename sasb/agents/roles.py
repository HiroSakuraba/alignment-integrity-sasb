"""Four-role swarm used by the Stage A harness."""

DEFAULT_ROSTER = (
    {"agent_id": "planner-1", "role": "planner", "model": "scripted"},
    {"agent_id": "worker-1", "role": "worker", "model": "scripted"},
    {"agent_id": "reviewer-1", "role": "reviewer", "model": "scripted"},
    {"agent_id": "coordinator-1", "role": "coordinator", "model": "scripted"},
)
