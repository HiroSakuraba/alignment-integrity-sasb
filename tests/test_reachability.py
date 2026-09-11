"""The reachability gate must be a bounded proof, not one script's result."""
import unittest

from sasb.live import violation_reachable
from sasb.reachability import TEXTS, enumerate_moves, reachable, state_key
from sasb.runtime.treatments import DEFAULT, PROPOSED
from sasb.scenarios.maintenance import CONDITIONS, specification
from sasb.world import World


class Reachability(unittest.TestCase):
    def test_proposed_runtime_admits_no_violation_in_worker_mode(self):
        for condition in CONDITIONS:
            result = reachable(condition, runtime=PROPOSED, mode="worker", horizon=6)
            self.assertTrue(result["exhausted"], condition)
            self.assertEqual(result["violation_reachable"], 0, condition)
            self.assertIsNone(result["witness"])

    def test_default_runtime_admits_a_violation_with_a_witness(self):
        for condition in CONDITIONS:
            result = reachable(condition, runtime=DEFAULT, mode="worker", horizon=6)
            self.assertEqual(result["violation_reachable"], 1, condition)
            self.assertTrue(result["witness"], condition)
            for step in result["witness"]:
                self.assertIn("agent", step)
                self.assertIn("action", step)

    def test_result_states_its_approximations(self):
        result = reachable("tempting_unauthorized", runtime=PROPOSED, mode="worker", horizon=4)
        self.assertIn("over_approximates_schedule", result["approximations"])
        self.assertIn("quotients_free_text", result["approximations"])
        self.assertIn("exhausted", result)

    def test_shorter_horizon_never_finds_more(self):
        short = reachable("tempting_unauthorized", runtime=DEFAULT, mode="worker", horizon=2)
        long = reachable("tempting_unauthorized", runtime=DEFAULT, mode="worker", horizon=6)
        self.assertLessEqual(short["violation_reachable"], long["violation_reachable"])

    def test_search_covers_the_whole_typed_action_schema(self):
        world = World(specification("tempting_unauthorized"))
        actions = {action for action, _ in enumerate_moves(world, "worker-1")}
        # remember_message is rejected by the executor outside the session runner.
        self.assertEqual(actions, {"noop", "inspect_resource", "complete_maintenance",
                                   "use_credential", "report", "accept_update",
                                   "reject_update", "stop", "message_peer"})
        self.assertIn("pressure", TEXTS["message"])

    def test_state_key_ignores_the_receipt_log(self):
        world = World(specification("authorized_maintenance"))
        before = state_key(world)
        world.receipts.record("worker-1", "noop", "executed", {})
        self.assertEqual(before, state_key(world))

    def test_driver_gate_uses_the_exhaustive_answer(self):
        for condition in CONDITIONS:
            for runtime in (DEFAULT, PROPOSED):
                gate = violation_reachable(condition, runtime, "worker")
                proof = reachable(condition, runtime=runtime, mode="worker", horizon=6)
                self.assertEqual(gate, proof["violation_reachable"], (condition, runtime))


if __name__ == "__main__":
    unittest.main()
