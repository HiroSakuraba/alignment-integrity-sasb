import unittest

from sasb.runtime.spaces import FORBIDDEN_AGENT_FIELDS, InformationSpaces, SpaceError


class SpaceTests(unittest.TestCase):
    def test_rejects_hidden_labels(self):
        spaces = InformationSpaces()
        for field in FORBIDDEN_AGENT_FIELDS:
            with self.subTest(field=field):
                with self.assertRaises(SpaceError):
                    spaces.publish("worker-1", {field: True, "task": "ok"})

    def test_evaluator_state_is_not_in_observations(self):
        spaces = InformationSpaces()
        spaces.set_evaluator(attack_status="injected", peer_compromised=True)
        spaces.publish("worker-1", {"task": "maintain test-db", "ownership": {"tenant": "tenant_a"}})
        observation = spaces.observe("worker-1")
        self.assertNotIn("attack_status", observation)
        self.assertNotIn("peer_compromised", observation)
        self.assertEqual(spaces.evaluator_get("attack_status"), "injected")


if __name__ == "__main__":
    unittest.main()
