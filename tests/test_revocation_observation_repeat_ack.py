import unittest

from sasb.executor import Executor
from sasb.scenarios.maintenance import specification
from sasb.world import World


class RepeatAcknowledgmentTests(unittest.TestCase):
    def test_repeat_ack_cannot_restore_write_capability(self):
        world = World(specification("valid_stop"), revocation_observation_mode="persistent")
        executor = Executor(world)
        for _ in range(6):
            receipt = executor.apply("worker-1", "accept_update", {"kind": "revoke"})
            self.assertEqual(receipt["decision"], "executed")
            self.assertFalse(world.capabilities.authorized("worker-1", "write", "test-db", "tenant_a"))
        self.assertEqual(world.resources.writes, [])


if __name__ == "__main__":
    unittest.main()
