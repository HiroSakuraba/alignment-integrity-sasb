"""Exhaustive bounded reachability over SASB world state.

`violation_reachable` in the live driver runs one scripted noncompliant episode
and reports whether that script reached a prohibited effect. A zero from it
means "this script did not manage it", not "no sequence of legal actions can".
This module answers the second question instead, the way controlled_ai.solver
does for the finite model: breadth-first over reachable world states up to a
fixed horizon, deduplicating states, returning a witness sequence when one
exists.

Two deliberate approximations, both stated in the result so no reader has to
infer them:

over_approximates_schedule
    The search lets any listed agent move at any step, which is a superset of
    the harness turn order. So `reachable=0` is sound: if no interleaving can
    reach a violation, the harness schedule cannot either. `reachable=1` may
    name a sequence the harness schedule would not itself produce, which costs
    money (a cell gets paid for) but never hides a violation.

quotients_free_text
    Message bodies, report risk and evidence strings, and stop or reject
    reasons are unbounded, so the search uses a small canonical vocabulary for
    each rather than all strings. The abstraction is sound as long as the
    executor's effects depend on these fields only through the canonical
    distinctions listed in TEXTS, which is true of the current executor: it
    stores or forwards them but never branches on their content. If that stops
    being true, this note has to change with it.

Receipts and the event log are excluded from the state key. They grow with
every action and never shrink, so including them would make every state unique
and defeat deduplication. They are outputs of the trajectory, not inputs to
what can happen next.
"""
from __future__ import annotations

import json
from collections import deque
from copy import deepcopy

from .agents.roles import DEFAULT_ROSTER
from .executor import Executor, completed_violation
from .runtime.treatments import DEFAULT, PROPOSED
from .scenarios.maintenance import specification
from .world import World

TURN_ORDER = tuple(row["agent_id"] for row in DEFAULT_ROSTER)

# Canonical stand-ins for unbounded string fields. See quotients_free_text.
TEXTS = {
    "message": ("benign", "pressure"),
    "reason": ("stated",),
    "risk": ("unauthorized_write",),
    "evidence": ("resource-service",),
    "kind": ("official", "unofficial"),
}


def enumerate_moves(world, agent_id):
    """Every typed action the schema admits for this agent, with small argument sets."""
    spec = world.spec
    tenants = sorted(world.resources.tenants)
    resources = sorted({spec["authorized_resource"], spec["forbidden_resource"]})
    credentials = sorted({spec["authorized_credential"], spec["forbidden_credential"]})
    peers = [a for a in TURN_ORDER if a != agent_id]

    moves = [("noop", {})]
    moves += [("inspect_resource", {"tenant": t}) for t in tenants]
    moves += [("complete_maintenance", {"resource": r}) for r in resources]
    moves += [("use_credential", {"credential": c, "resource": r})
              for c in credentials for r in resources]
    moves += [("report", {"risk": risk, "evidence": ev})
              for risk in TEXTS["risk"] for ev in TEXTS["evidence"]]
    moves += [("accept_update", {"kind": k}) for k in TEXTS["kind"]]
    moves += [("reject_update", {"reason": r}) for r in TEXTS["reason"]]
    moves += [("stop", {"reason": r}) for r in TEXTS["reason"]]
    moves += [("message_peer", {"to": p, "text": t})
              for p in peers for t in TEXTS["message"]]
    return moves


def state_key(world):
    """Canonical form of everything that determines what can happen next."""
    return json.dumps({
        "runtime": world.runtime,
        "writes": sorted(map(str, world.resources.writes)),
        "workspace": sorted((k, str(v)) for k, v in world.workspace.files.items()),
        "stopped": sorted(world.stopped_agents),
        "evidence": sorted("|".join(map(str, k)) for k in world.resource_evidence),
        "grants": sorted(map(str, getattr(world.capabilities, "grants", ()) or ())),
        "reports": sorted(json.dumps(r, sort_keys=True, default=str)
                          for r in world.reports.delivered()),
    }, sort_keys=True)


def reachable(condition, runtime=PROPOSED, mode="worker", horizon=6, agents=None,
              max_states=200000):
    """Breadth-first search for a prohibited effect within `horizon` actions.

    Returns 1 with a witness, 0 for exhausted exclusion, or None on truncation.
    This search covers the maintenance fixture, not the repeated-job extension.
    """
    if runtime not in {DEFAULT, PROPOSED}:
        raise ValueError("unknown runtime")
    if mode not in {"worker", "swarm"}:
        raise ValueError("unknown mode")
    if type(horizon) is not int or horizon < 0:
        raise ValueError("horizon must be a nonnegative integer")
    if type(max_states) is not int or max_states < 1:
        raise ValueError("max_states must be a positive integer")
    if agents is None:
        agents = ("worker-1",) if mode == "worker" else TURN_ORDER

    start = World(specification(condition), runtime=runtime)
    if completed_violation(start):
        return _result(condition, runtime, mode, horizon, agents, 1, [], 1, True, 0)

    seen = {state_key(start): 0}
    queue = deque([(start, [], 0)])
    explored = 0
    truncated = False

    while queue:
        world, path, depth = queue.popleft()
        if depth >= horizon:
            continue
        for agent_id in agents:
            if agent_id in world.stopped_agents:
                continue
            for action, arguments in enumerate_moves(world, agent_id):
                nxt = deepcopy(world)
                Executor(nxt).apply(agent_id, action, arguments)
                explored += 1
                step = {"agent": agent_id, "action": action, "arguments": arguments}
                if completed_violation(nxt):
                    return _result(condition, runtime, mode, horizon, agents,
                                   1, path + [step], len(seen), True, explored)
                key = state_key(nxt)
                if key in seen and seen[key] <= depth + 1:
                    continue
                seen[key] = depth + 1
                if len(seen) > max_states:
                    truncated = True
                    queue.clear()
                    break
                queue.append((nxt, path + [step], depth + 1))
            if truncated:
                break
        if truncated:
            break

    return _result(condition, runtime, mode, horizon, agents, 0, None,
                   len(seen), not truncated, explored)


def _result(condition, runtime, mode, horizon, agents, found, witness, states,
            exhausted, explored):
    return {
        "condition": condition,
        "runtime": runtime,
        "mode": mode,
        "horizon": horizon,
        "agents": list(agents),
        "violation_reachable": found if found or exhausted else None,
        "witness": witness,
        "distinct_states": states,
        "transitions_explored": explored,
        "exhausted": exhausted,
        "claim": (
            "Witness sequence reaches a prohibited effect."
            if found else
            "No legal action sequence within the horizon reaches a prohibited effect."
            if exhausted else
            "State cap reached before the search finished; not a proof of safety."
        ),
        "approximations": ["over_approximates_schedule", "quotients_free_text"],
    }


def map_all(runtime=PROPOSED, mode="worker", horizon=6, conditions=None):
    from .scenarios.maintenance import CONDITIONS
    return [reachable(c, runtime=runtime, mode=mode, horizon=horizon)
            for c in (conditions or CONDITIONS)]


if __name__ == "__main__":
    print(json.dumps(map_all(), indent=2, sort_keys=True))
