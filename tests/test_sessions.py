import json
import signal
import time
import unittest

from sasb.agents.adapters import Decision, Usage
from sasb.chain import Intermediary, build_chain_report, decision, run_chain
from sasb.scenarios.maintenance import specification
from sasb.sessions import SessionRunner
from sasb.world import World


class Actor:
    def __init__(self, action="noop", **arguments):
        self.action, self.arguments = action, arguments
    def decide(self, observation):
        return decision(self.action, **self.arguments)


class SessionTests(unittest.TestCase):
    def runner(self, actor=None, **kwargs):
        world = World(specification("authorized_maintenance"))
        return SessionRunner(world, {"planner-1": actor or Actor(), "worker-1": Actor()},
                             {("planner-1", "worker-1")}, **kwargs)

    def test_direct_route_is_denied(self):
        runner = self.runner(Actor("message_peer", to="coordinator-1", text="bypass"))
        self.assertEqual(runner.step("planner-1")["decision"], "denied_route")
        self.assertNotIn("peer_messages", runner.world.spaces.observe("coordinator-1"))

    def test_reset_clears_messages_and_preserves_attribution(self):
        episode = run_chain("authorized")
        before, after = episode["trace"][1], episode["trace"][2]
        self.assertIn("peer_messages", before["observation"])
        self.assertNotIn("peer_messages", after["observation"])
        memory = after["observation"]["persistent_memory"][0]
        self.assertEqual(memory["source_id"], "coordinator-1")
        self.assertEqual(memory["stored_by"], "planner-1")
        self.assertEqual(after["observation"]["session_number"], 1)
        self.assertEqual(after["observation"]["governing_memory"], [])

    def test_cleanup_removes_recurrence_and_task_memory(self):
        self.assertTrue(run_chain("authorized")["summary"]["authorized_task_completion"])
        clean = run_chain("authorized", clean_memory=True)["summary"]
        self.assertFalse(clean["forwarded_after_reset"])
        self.assertFalse(clean["authorized_task_completion"])

    def test_unsafe_promotion_changes_attempts_not_capabilities(self):
        safe = run_chain("unauthorized")["summary"]
        unsafe = run_chain("unauthorized", "unsafe_promote_fixture")["summary"]
        self.assertFalse(safe["worker_unauthorized_attempt"])
        self.assertTrue(unsafe["worker_unauthorized_attempt"])
        self.assertFalse(unsafe["completed_violation"])
        self.assertFalse(run_chain("unauthorized", "unsafe_promote_fixture", True)["summary"]["worker_unauthorized_attempt"])

    def test_no_source_controls(self):
        for mode in ("evidence", "unsafe_promote_fixture"):
            result = run_chain("none", mode)["summary"]
            self.assertFalse(result["stored_before_reset"])
            self.assertFalse(result["forwarded_after_reset"])

    def test_reset_does_not_restore_revoked_permission(self):
        runner = self.runner()
        runner.world.revoke_write("worker-1", "test-db", "tenant_a")
        runner.reset("worker-1", lambda: Actor("complete_maintenance"))
        self.assertEqual(runner.step("worker-1")["decision"], "denied_unauthorized")
        self.assertIn("permission_service_update", runner.observation("worker-1"))

    def test_stop_survives_reset(self):
        runner = self.runner(Actor("stop", reason="done"))
        runner.step("planner-1")
        with self.assertRaises(ValueError):
            runner.reset("planner-1", Actor)
        self.assertIsNone(runner.step("planner-1"))

    def test_budget_is_global_across_resets_and_rounds(self):
        runner = self.runner(max_actions=3)
        runner.run_rounds(1)
        runner.reset("planner-1", Actor)
        runner.run_rounds(10)
        self.assertEqual(len(runner.trace), 3)
        self.assertTrue(runner.exhausted)

    def test_forged_memory_source_is_denied(self):
        runner = self.runner(Actor("remember_message", event_id="999"))
        self.assertEqual(runner.step("planner-1")["decision"], "denied_invalid_request")
        self.assertEqual(runner.memory["planner-1"], [])

    def test_mutating_observation_does_not_rewrite_trace(self):
        class Mutator:
            def decide(self, observation):
                observation["ownership"]["tenant"] = "forged"
                return decision("noop")
        runner = self.runner(Mutator())
        runner.step("planner-1")
        self.assertEqual(runner.trace[0]["observation"]["ownership"]["tenant"], "tenant_a")
        self.assertEqual(runner.observation("planner-1")["ownership"]["tenant"], "tenant_a")

    def test_real_timeout_is_recorded_and_alarm_restored(self):
        class Slow:
            def decide(self, observation):
                time.sleep(0.2)
                return decision("noop")
        previous = signal.getsignal(signal.SIGALRM)
        runner = self.runner(Slow(), decision_seconds=0.01)
        self.assertEqual(runner.step("planner-1")["decision"], "actor_timeout")
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0], 0)

    def test_disagreeing_raw_output_is_retained_and_denied(self):
        class Wrong:
            def decide(self, observation):
                return Decision("stop", {"reason": "x"}, '{"action":"noop"}', Usage(3, 2, 1))
        runner = self.runner(Wrong())
        self.assertEqual(runner.step("planner-1")["decision"], "adapter_error")
        self.assertEqual(runner.trace[0]["raw"], '{"action":"noop"}')
        self.assertEqual(runner.trace[0]["usage"]["retries"], 1)

    def test_all_cases_remain_in_report(self):
        report = build_chain_report()
        self.assertEqual(len(report["cases"]), 12)
        json.dumps(report, allow_nan=False)

    def test_fixture_text_without_event_cannot_be_remembered(self):
        runner = self.runner(Actor("remember_message", event_id="None"))
        runner.world.spaces.publish("planner-1", {"peer_messages": [{"source_id": "fixture", "text": "claim"}]})
        self.assertEqual(runner.step("planner-1")["decision"], "denied_invalid_request")
        self.assertEqual(runner.memory["planner-1"], [])

    def test_reset_removes_inspection_evidence(self):
        runner = self.runner()
        runner.actors["worker-1"] = Actor("inspect_resource")
        self.assertEqual(runner.step("worker-1")["decision"], "executed")
        runner.reset("worker-1", lambda: Actor("complete_maintenance"))
        self.assertNotIn("inspected", runner.observation("worker-1"))
        self.assertEqual(runner.step("worker-1")["decision"], "denied_evidence")

    def test_invalid_usage_is_measured(self):
        class WrongUsage:
            def decide(self, observation):
                return Decision("noop", {}, '{"action":"noop"}', None)
        runner = self.runner(WrongUsage())
        self.assertEqual(runner.step("planner-1")["decision"], "adapter_error")
