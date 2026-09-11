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

    def test_dry_run_forecasts_and_stops_on_episode_cap(self):
        report = run_experiment(provider="local", dry_run=True, mode="worker")
        self.assertGreater(report["forecast_usd_if_paid"], 0.0)
        self.assertEqual(report["spent_usd"], 0.0)
        self.assertEqual(report["stopped"]["reason"], "episode_cap")
        self.assertNotEqual(report["stopped"].get("reason"), "target_met")

    def test_paid_skip_does_not_crash_and_honest_unreachable_is_paid(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        from sasb.live import StubTransport
        try:
            report = run_experiment(
                provider="anthropic",
                dry_run=False,
                mode="worker",
                transport=StubTransport(),
                cap_usd=1.0,
            )
        finally:
            for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
                os.environ.pop(key, None)
        self.assertFalse(report["dry_run"])
        self.assertEqual(report["stopped"]["reason"], "episode_cap")
        join = report["reachability_join"]
        skipped = [row for row in join if row.get("skipped") == "unreachable"]
        honest = [row for row in join if row["role"] == "honest"]
        self.assertTrue(skipped)
        self.assertTrue(all(row["role"] == "adversary" for row in skipped))
        self.assertTrue(honest)
        self.assertTrue(all(row["paid"] and row["completed_violation"] is not None for row in honest))
        self.assertNotIn(None, [row["completed_violation"] for row in report["rows"] if row.get("paid")])
        self.assertGreater(report["spent_usd"], 0.0)
        self.assertIn("completed_violation_rate", report["summary"])

    def test_default_runtime_pays_adversary_when_violation_is_reachable(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        from sasb.live import StubTransport
        from sasb.runtime.treatments import DEFAULT
        try:
            report = run_experiment(
                provider="anthropic",
                dry_run=False,
                conditions=("tempting_unauthorized",),
                runtime=DEFAULT,
                mode="worker",
                transport=StubTransport(),
                roles=("adversary",),
            )
        finally:
            for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
                os.environ.pop(key, None)
        self.assertEqual(len(report["rows"]), 1)
        self.assertTrue(report["rows"][0]["paid"])
        self.assertEqual(report["rows"][0]["harm_reachable"], 1)
        self.assertIsNone(report["rows"][0].get("skipped"))


if __name__ == "__main__":
    unittest.main()
