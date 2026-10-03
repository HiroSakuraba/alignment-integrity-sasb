import unittest

from sasb.executor import Executor
from sasb.observations import enrich_observation
from sasb.scenarios.maintenance import specification
from sasb.world import World


class RevocationObservationAuthorityTests(unittest.TestCase):
    def test_visibility_never_controls_authority(self):
        for mode in ("persistent", "acknowledged", "consumed"):
            with self.subTest(mode=mode):
                world = World(specification("valid_stop"), revocation_observation_mode=mode)
                update = world.spaces.runtime_view()["permission_service_updates"]["worker-1"]
                Executor(world).apply("worker-1", "accept_update", {"kind": update["kind"]})
                enrich_observation(world, "worker-1")
                self.assertFalse(world.capabilities.authorized("worker-1", "write", "test-db", "tenant_a"))


if __name__ == "__main__":
    unittest.main()
