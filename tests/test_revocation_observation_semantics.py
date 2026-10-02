import unittest

from sasb.executor import Executor
from sasb.observations import enrich_observation
from sasb.scenarios.maintenance import specification
from sasb.world import World


class RevocationObservationSemanticsTests(unittest.TestCase):
    def _world(self, mode):
        return World(specification("valid_stop"), revocation_observation_mode=mode)

    def _ack(self, world):
        update = world.spaces.runtime_view()["permission_service_updates"]["worker-1"]
        receipt = Executor(world).apply("worker-1", "accept_update", {"kind": "revoke"})
        return update, receipt

    def test_all_modes_are_identical_before_ack(self):
        observations = []
        for mode in ("persistent", "acknowledged", "consumed"):
            world = self._world(mode)
            observations.append(enrich_observation(world, "worker-1")["permission_service_update"])
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[1], observations[2])

    def test_persistent_keeps_update_unchanged_after_ack(self):
        world = self._world("persistent")
        update, receipt = self._ack(world)
        self.assertEqual(receipt["decision"], "executed")
        observation = enrich_observation(world, "worker-1")
        self.assertEqual(observation["permission_service_update"], update)
        self.assertNotIn("acknowledged", observation["permission_service_update"])

    def test_acknowledged_marks_handled_update(self):
        world = self._world("acknowledged")
        update, receipt = self._ack(world)
        self.assertEqual(receipt["decision"], "executed")
        observation = enrich_observation(world, "worker-1")
        self.assertEqual(observation["permission_service_update"]["update_id"], update["update_id"])
        self.assertIs(observation["permission_service_update"]["acknowledged"], True)

    def test_consumed_removes_active_update_after_ack(self):
        world = self._world("consumed")
        _, receipt = self._ack(world)
        self.assertEqual(receipt["decision"], "executed")
        observation = enrich_observation(world, "worker-1")
        self.assertNotIn("permission_service_update", observation)

    def test_ack_does_not_restore_revoked_write_authority(self):
        for mode in ("persistent", "acknowledged", "consumed"):
            with self.subTest(mode=mode):
                world = self._world(mode)
                self._ack(world)
                runtime = world.spaces.runtime_view()
                self.assertNotIn("worker-1", runtime["permissions"])
                receipt = Executor(world).apply("worker-1", "complete_maintenance", {"resource": "test-db"})
                self.assertEqual(receipt["decision"], "denied_unauthorized")
                self.assertEqual(world.resources.writes, [])

    def test_repeat_ack_is_behavior_only(self):
        world = self._world("acknowledged")
        update, first = self._ack(world)
        second = Executor(world).apply("worker-1", "accept_update", {"kind": "revoke"})
        self.assertEqual(first["decision"], "executed")
        self.assertEqual(second["decision"], "executed")
        self.assertIn(update["update_id"], world.acknowledged_updates["worker-1"])
        self.assertNotIn("worker-1", world.spaces.runtime_view()["permissions"])

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            World(specification("valid_stop"), revocation_observation_mode="mystery")


if __name__ == "__main__":
    unittest.main()
