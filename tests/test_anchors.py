import unittest

from sasb.harness import run_anchors, run_episode
from sasb.runtime.spaces import FORBIDDEN_AGENT_FIELDS
from sasb.scenarios.maintenance import CONDITIONS


class AnchorTests(unittest.TestCase):
    def test_worker_only_matrix_has_ten_episodes(self):
        matrix = run_anchors()
        self.assertEqual(matrix["summary"]["episodes"], 10)
        self.assertTrue(all(episode["mode"] == "worker" for episode in matrix["episodes"]))

    def test_compliant_authorized_anchor_completes(self):
        episode = run_episode("authorized_maintenance", "compliant", mode="worker")
        self.assertTrue(episode["score"]["authorized_task_completion"])
        self.assertFalse(episode["score"]["completed_violation"])
        self.assertTrue(all(item["agent_id"] == "worker-1" for item in episode["receipts"]))

    def test_noncompliant_anchor_is_blocked_under_proposed_runtime(self):
        episode = run_episode("tempting_unauthorized", "noncompliant", mode="worker")
        self.assertTrue(episode["score"]["unauthorized_attempt"])
        self.assertFalse(episode["score"]["completed_violation"])

    def test_anchors_do_not_leak_hidden_labels(self):
        for condition in CONDITIONS:
            episode = run_episode(condition, "compliant", mode="worker")
            leaked = FORBIDDEN_AGENT_FIELDS.intersection(episode["agent_observation_keys"])
            self.assertFalse(leaked, leaked)


if __name__ == "__main__":
    unittest.main()
