"""Regression cases that the original happy-path matrix did not exercise."""

import unittest

from sasb.agents.adapters import AdapterError, parse_decision
from sasb.executor import Executor, completed_violation
from sasb.runtime.capabilities import CapabilityService
from sasb.runtime.spaces import InformationSpaces, SpaceError
from sasb.scenarios.maintenance import specification
from sasb.world import World


class IntegrityRegressionTests(unittest.TestCase):
    def test_hidden_label_inside_list_is_rejected(self):
        with self.assertRaises(SpaceError):
            InformationSpaces().publish("worker-1", {"messages": [{"peer_compromised": True}]})

    def test_observation_cannot_rewrite_shared_state(self):
        spaces = InformationSpaces()
        payload = {"ownership": {"tenant": "tenant_a"}}
        spaces.publish("worker-1", payload)
        payload["ownership"]["tenant"] = "source-mutated"
        observation = spaces.observe("worker-1")
        observation["ownership"]["tenant"] = "reader-mutated"
        self.assertEqual(spaces.observe("worker-1")["ownership"]["tenant"], "tenant_a")

    def test_delegation_does_not_outlive_parent(self):
        caps = CapabilityService()
        caps.grant("worker", "write", "db", "tenant", expires_at=1)
        caps.delegate("worker", "reviewer", "write", "db", "tenant")
        caps.tick()
        self.assertFalse(caps.authorized("reviewer", "write", "db", "tenant"))

    def test_parent_revocation_invalidates_delegation(self):
        caps = CapabilityService()
        caps.grant("worker", "write", "db", "tenant")
        caps.delegate("worker", "reviewer", "write", "db", "tenant")
        caps.revoke("worker", "write", "db", "tenant")
        self.assertFalse(caps.authorized("reviewer", "write", "db", "tenant"))

    def test_revocation_applies_without_agent_acceptance(self):
        world = World(specification("valid_stop"))
        receipt = Executor(world).apply("worker-1", "complete_maintenance", {"resource": "test-db"})
        self.assertEqual(receipt["decision"], "denied_unauthorized")
        self.assertEqual(world.resources.writes, [])

    def test_stop_is_terminal_for_the_actor(self):
        world = World(specification("authorized_maintenance"))
        executor = Executor(world)
        executor.apply("worker-1", "inspect_resource", {"tenant": "tenant_a"})
        executor.apply("worker-1", "stop", {"reason": "finished"})
        receipt = executor.apply("worker-1", "complete_maintenance", {"resource": "test-db"})
        self.assertEqual(receipt["decision"], "denied_stopped")
        self.assertEqual(world.resources.writes, [])

    def test_in_scope_write_after_revocation_is_still_a_violation(self):
        world = World(specification("valid_stop"))
        # Deliberately bypass the trusted boundary to falsify the outcome checker.
        world.resources.apply_write("cred_a", "test-db")
        self.assertTrue(completed_violation(world))

    def test_malformed_actions_use_one_error_type(self):
        for raw in ('null', '[]', '1', '{"action": []}',
                    '{"action":"noop","arguments":[]}',
                    '{"action":"use_credential","arguments":{}}'):
            with self.subTest(raw=raw), self.assertRaises(AdapterError):
                parse_decision(raw)


if __name__ == "__main__":
    unittest.main()
