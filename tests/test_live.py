import os
import unittest

from sasb.agents.providers import ProviderDisabled
from sasb.costs import usage_usd
from sasb.harness import run_episode
from sasb.live import actors_for_live, run_experiment
from sasb.runtime.spaces import FORBIDDEN_AGENT_FIELDS
from tests.test_providers import FakeTransport, _anthropic_body


class LiveDriverTests(unittest.TestCase):
    def test_dry_run_stays_offline_and_keeps_actions_in_observation(self):
        report = run_experiment(provider="local", dry_run=True, mode="worker")
        self.assertTrue(report["dry_run"])
        self.assertFalse(report["network_called"])
        self.assertEqual(report["provider"], "local")
        self.assertIsNone(report["model"])
        self.assertEqual(report["spent_usd"], 0.0)
        self.assertEqual(len(report["rows"]), 10)
        self.assertTrue(all(row["observation_has_available_actions"] for row in report["rows"]))
        self.assertIn("completed_violation_rate", report["summary"])

    def test_live_path_stays_gated(self):
        os.environ.pop("SASB_ENABLE_NETWORK", None)
        os.environ.pop("SASB_PROVIDER_VALIDATED", None)
        with self.assertRaises(ProviderDisabled):
            run_experiment(provider="anthropic", dry_run=False)

    def test_fake_transport_worker_records_usage_and_provider(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        try:
            body = _anthropic_body('{"action":"inspect_resource","arguments":{"tenant":"tenant_a"}}')
            transport = FakeTransport(body=body)
            report = run_experiment(
                provider="anthropic",
                dry_run=False,
                conditions=("authorized_maintenance",),
                mode="worker",
                transport=transport,
                cap_usd=1.0,
            )
        finally:
            for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
                os.environ.pop(key, None)
        self.assertFalse(report["dry_run"])
        self.assertEqual(report["provider"], "anthropic")
        self.assertEqual(report["rows"][0]["model"], "claude-haiku-4-5-20251001")
        self.assertGreater(report["usage"]["input_tokens"], 0)
        self.assertGreater(report["spent_usd"], 0.0)
        self.assertLess(report["spent_usd"], 0.01)
        self.assertTrue(transport.capture)

    def test_schema_failure_is_an_outcome_and_keeps_spent_tokens(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        try:
            transport = FakeTransport(body=_anthropic_body("not json"))
            actors = actors_for_live("authorized_maintenance", "anthropic", transport=transport)
            episode = run_episode(
                "authorized_maintenance",
                "model",
                mode="worker",
                actors=actors,
                provider="anthropic",
            )
        finally:
            for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
                os.environ.pop(key, None)
        self.assertTrue(episode["score"]["invalid_action_or_actor_error"])
        self.assertGreater(episode["usage"]["input_tokens"], 0)
        self.assertFalse(episode["completed_violation"])

    def test_live_observation_does_not_leak_evaluator_fields(self):
        from sasb.observations import enrich_observation
        from sasb.scenarios.maintenance import specification
        from sasb.world import World

        observation = enrich_observation(World(specification("tempting_unauthorized")), "worker-1")
        self.assertTrue(FORBIDDEN_AGENT_FIELDS.isdisjoint(observation))
        self.assertIn("inspect_resource", observation["available_actions"])

    def test_usage_prices_reported_tokens(self):
        cost = usage_usd("claude-haiku-4-5-20251001", {"input_tokens": 200, "output_tokens": 20})
        self.assertGreater(cost, 0.0)
        self.assertLess(cost, 0.01)


if __name__ == "__main__":
    unittest.main()
