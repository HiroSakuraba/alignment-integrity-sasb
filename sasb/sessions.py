"""Bounded local actor sessions with attributed persistent message memory.

Actor code and factories are trusted Python. This is not process isolation.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import signal
import threading

from .agents.adapters import AdapterError, Decision, Usage, parse_decision
from .executor import Executor
from .observations import enrich_observation


@contextmanager
def deadline(seconds):
    """Interrupt a local decide call on POSIX's main thread; never silently disable."""
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
        raise RuntimeError("local actor deadlines require a POSIX main thread")
    if signal.getitimer(signal.ITIMER_REAL)[0]:
        raise RuntimeError("an existing alarm would conflict with the actor deadline")
    def expired(signum, frame):
        raise TimeoutError("actor decision deadline exceeded")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class SessionRunner:
    def __init__(self, world, actors, edges, max_actions=32, decision_seconds=1.0,
                 memory_mode="evidence"):
        if type(max_actions) is not int or max_actions < 1:
            raise ValueError("max_actions must be a positive integer")
        if not isinstance(decision_seconds, (int, float)) or not 0 < decision_seconds < float("inf"):
            raise ValueError("decision_seconds must be positive and finite")
        if memory_mode not in {"evidence", "unsafe_promote_fixture"}:
            raise ValueError("unknown memory mode")
        if not set(actors).issubset(world.roster.agents):
            raise ValueError("actor outside roster")
        self.edges = frozenset(edges)
        if any(a not in actors or b not in actors for a, b in self.edges):
            raise ValueError("edge outside actor set")
        self.world, self.actors = world, dict(actors)
        self.executor = Executor(world)
        self.max_actions, self.decision_seconds = max_actions, decision_seconds
        self.memory_mode = memory_mode
        self.memory = {a: [] for a in actors}
        self.baseline = {a: world.spaces.observe(a) for a in actors}
        self.sessions = {a: 0 for a in actors}
        self.trace = []
        self.resets = []
        self.exhausted = False

    def observation(self, agent):
        observation = self.world.spaces.observe(agent)
        observation["session_number"] = self.sessions[agent]
        observation["persistent_memory"] = deepcopy(self.memory[agent])
        # Named unsafe fixture changes presentation only, never capability grants.
        observation["governing_memory"] = (
            deepcopy(self.memory[agent]) if self.memory_mode == "unsafe_promote_fixture" else []
        )
        return enrich_observation(self.world, agent, observation)

    def reset(self, agent, factory, clean_memory=False):
        """Controller-only reset; budgets, receipts, revocations and stop survive."""
        if agent in self.world.stopped_agents:
            raise ValueError("reset cannot restart a stopped actor")
        replacement = factory()
        if replacement is self.actors[agent]:
            raise ValueError("reset requires a fresh actor instance")
        self.actors[agent] = replacement
        self.sessions[agent] += 1
        if clean_memory:
            self.memory[agent] = []
        fresh = deepcopy(self.baseline[agent])
        fresh.pop("peer_messages", None)
        fresh.pop("inspected", None)
        fresh.pop("permission_service_update", None)
        update = self.world.spaces.runtime_view().get("permission_service_updates", {}).get(agent)
        if update:
            fresh["permission_service_update"] = update
        self.world.spaces.observations[agent] = fresh
        for key in list(self.world.resource_evidence):
            if key[0] == agent:
                del self.world.resource_evidence[key]
        self.resets.append({"agent_id": agent, "session_number": self.sessions[agent],
                            "after_actions": len(self.trace), "clean_memory": clean_memory})

    def _apply(self, agent, action, arguments):
        if action == "remember_message":
            if set(arguments) != {"event_id"} or not isinstance(arguments["event_id"], str):
                raise AdapterError("remember_message requires a string event_id")
            message = next((m for m in self.world.spaces.observe(agent).get("peer_messages", [])
                            if "event_id" in m and str(m["event_id"]) == arguments["event_id"]), None)
            if message is None:
                receipt = self.world.receipts.record(agent, action, "denied_invalid_request", {})
            else:
                entry = deepcopy(message)
                entry["stored_by"] = agent
                entry["stored_in_session"] = self.sessions[agent]
                if not any(m["event_id"] == entry["event_id"] for m in self.memory[agent]):
                    self.memory[agent].append(entry)
                receipt = self.world.receipts.record(agent, action, "executed", {"event_id": entry["event_id"]})
            self.world.capabilities.tick()
            return receipt
        if action == "message_peer" and (agent, arguments["to"]) not in self.edges:
            self.world.capabilities.tick()
            return self.world.receipts.record(agent, action, "denied_route", {"to": arguments["to"]})
        return self.executor.apply(agent, action, arguments)

    def step(self, agent):
        if agent not in self.actors:
            raise ValueError("unknown session actor")
        if agent in self.world.stopped_agents:
            return None
        if len(self.trace) >= self.max_actions:
            self.exhausted = True
            return None
        observation = self.observation(agent)
        row = {"agent_id": agent, "session_number": self.sessions[agent],
               "observation": deepcopy(observation), "raw": None, "usage": None}
        try:
            with deadline(self.decision_seconds):
                decision = self.actors[agent].decide(deepcopy(observation))
            if not isinstance(decision, Decision):
                raise AdapterError("actor must return Decision")
            row["raw"] = decision.raw
            if not isinstance(decision.usage, Usage):
                raise AdapterError("actor must supply Usage")
            row["usage"] = asdict(decision.usage)
            if any(type(v) is not int or v < 0 for v in row["usage"].values()):
                raise AdapterError("usage must be nonnegative integer counts")
            # Parse the actual proposal; typed metadata cannot disagree with it.
            action, arguments = parse_decision(decision.raw)
            if (action, arguments) != (decision.action, decision.arguments):
                raise AdapterError("raw and structured decisions disagree")
            receipt = self._apply(agent, action, arguments)
        except (AdapterError, TimeoutError) as exc:
            status = "actor_timeout" if isinstance(exc, TimeoutError) else "adapter_error"
            receipt = self.world.receipts.record(agent, "invalid_output", status,
                                                 {"error_type": type(exc).__name__})
            self.world.stopped_agents.add(agent)
            self.world.capabilities.tick()
        row["receipt"] = deepcopy(receipt)
        self.trace.append(row)
        return deepcopy(receipt)

    def run_rounds(self, count):
        if type(count) is not int or count < 0:
            raise ValueError("round count must be nonnegative")
        for _ in range(count):
            for agent in self.actors:
                self.step(agent)
            if self.exhausted or all(a in self.world.stopped_agents for a in self.actors):
                break
        return deepcopy(self.trace)
