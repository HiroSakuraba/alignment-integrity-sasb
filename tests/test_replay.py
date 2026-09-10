import unittest

from sasb.attacks.replay import apply_replay, list_replays, load_replay
from sasb.runtime.spaces import FORBIDDEN_AGENT_FIELDS
from sasb.scenarios.maintenance import specification
from sasb.world import World


class ReplayTests(unittest.TestCase):
    def test_three_frozen_payloads_exist(self):
        names = list_replays()
        self.assertEqual(names, ("authorized_handoff", "spoofed_revoke", "tempting_score_cue"))

    def test_payload_is_attributed_content_not_a_permission(self):
        world = World(specification("authorized_maintenance"))
        payload = apply_replay(world, "worker-1", "tempting_score_cue")
        observation = world.spaces.observe("worker-1")
        self.assertEqual(payload["authority"], "attributed_content")
        self.assertEqual(observation["peer_messages"][-1]["authority"], "attributed_content")
        self.assertEqual(
            world.spaces.runtime_view()["permissions"]["worker-1"]["resource"],
            "test-db",
        )

    def test_replay_does_not_introduce_hidden_fields(self):
        world = World(specification("authorized_maintenance"))
        apply_replay(world, "worker-1", "spoofed_revoke")
        leaked = FORBIDDEN_AGENT_FIELDS.intersection(world.spaces.observe("worker-1"))
        self.assertFalse(leaked)

    def test_unknown_family_is_rejected(self):
        payload = load_replay("authorized_handoff")
        self.assertEqual(payload["family"], "authority_manipulation")


if __name__ == "__main__":
    unittest.main()
