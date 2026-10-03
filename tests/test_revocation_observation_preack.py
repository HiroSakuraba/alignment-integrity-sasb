import unittest

from sasb.observations import enrich_observation
from sasb.scenarios.maintenance import specification
from sasb.world import World


class RevocationObservationPreAckTests(unittest.TestCase):
    def test_only_post_ack_representation_varies(self):
        snapshots = []
        for mode in ("persistent", "acknowledged", "consumed"):
            world = World(specification("valid_stop"), revocation_observation_mode=mode)
            observation = enrich_observation(world, "worker-1")
            snapshots.append(observation)
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[1], snapshots[2])


if __name__ == "__main__":
    unittest.main()
