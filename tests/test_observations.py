import unittest

from sasb.observations import enrich_observation
from sasb.runtime.spaces import FORBIDDEN_AGENT_FIELDS
from sasb.scenarios.maintenance import specification
from sasb.world import World


class ObservationTests(unittest.TestCase):
    def test_envelope_is_agent_safe(self):
        world = World(specification("tempting_unauthorized"))
        observation = enrich_observation(world, "worker-1")
        self.assertIn("capability_summary", observation)
        self.assertIn("available_actions", observation)
        self.assertIn("own_receipts", observation)
        self.assertEqual(observation["capability_summary"]["runtime_treatment"], "proposed")
        leaked = FORBIDDEN_AGENT_FIELDS.intersection(observation)
        self.assertFalse(leaked)

    def test_record_has_no_network(self):
        from sasb.harness import run_episode
        record = run_episode("authorized_maintenance")["record"]
        self.assertFalse(record["network"])
        self.assertEqual(record["runtime_treatment"], "proposed")
        self.assertIn("worker-v1.txt", record["prompt_hashes"])


if __name__ == "__main__":
    unittest.main()
