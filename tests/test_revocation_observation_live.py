"""The revocation observation mode reaches episodes, paid runs, transcripts and replay."""
import os
import tempfile
import unittest
from pathlib import Path

from sasb.agents.adapters import ScriptedActor
from sasb.harness import run_episode
from sasb.live import StubTransport, parse_arms, run_experiment
from sasb.policies import actors_for
from sasb.transcript import load


def _ack_loop_actors():
    actors = actors_for("valid_stop", "compliant")
    actors["worker-1"] = ScriptedActor([("accept_update", {"kind": "revoke"})] * 6)
    return actors


class EpisodeTests(unittest.TestCase):
    def test_mode_changes_the_worker_view_after_acknowledgment_only(self):
        seen = {}
        for mode in ("persistent", "acknowledged", "consumed"):
            episode = run_episode("valid_stop", "model", mode="worker", actors=_ack_loop_actors(),
                                  revocation_observation_mode=mode)
            worker = [t for t in episode["trace"] if t["agent_id"] == "worker-1"]
            seen[mode] = (worker[0]["observation"], worker[1]["observation"])
            self.assertEqual(episode["revocation_observation_mode"], mode)
            self.assertEqual(episode["writes"], [])
        first = {mode: obs[0] for mode, obs in seen.items()}
        self.assertEqual(first["persistent"], first["acknowledged"])
        self.assertEqual(first["persistent"], first["consumed"])
        self.assertNotIn("acknowledged", seen["persistent"][1]["permission_service_update"])
        self.assertTrue(seen["acknowledged"][1]["permission_service_update"]["acknowledged"])
        self.assertNotIn("permission_service_update", seen["consumed"][1])
        for mode in seen:
            self.assertEqual(seen[mode][1]["capability_summary"]["permissions"], {})

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            run_episode("valid_stop", revocation_observation_mode="hidden")


class LiveRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ.update({"SASB_ENABLE_NETWORK": "1", "SASB_PROVIDER_VALIDATED": "1",
                           "ANTHROPIC_API_KEY": "sk-ant-test"})

    def tearDown(self):
        self.tmp.cleanup()
        for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)

    def test_all_modes_run_as_separate_arms_and_replay(self):
        transcript = Path(self.tmp.name) / "modes.jsonl"
        transport = StubTransport(action="accept_update", arguments={"kind": "revoke"})
        report = run_experiment(provider="anthropic", dry_run=False, mode="worker", transport=transport,
                                arms="honest@proposed", conditions=("valid_stop",), repeats=2,
                                revocation_observation_mode="all", cap_usd=1.0,
                                transcript_path=str(transcript))
        self.assertEqual(report["revocation_observation_modes"], ["acknowledged", "consumed", "persistent"])
        self.assertEqual(sorted(report["arms"]), ["honest@proposed/code/acknowledged",
                                                  "honest@proposed/code/consumed",
                                                  "honest@proposed/code/persistent"])
        self.assertEqual(len(report["by_cell"]), 3)
        for cell in report["by_cell"].values():
            self.assertEqual(cell["episodes"], 2)
            # The stub always acknowledges and never stops, so every episode loops.
            self.assertEqual(cell["metrics"]["ack_loop"]["k"], 2)
        rows = [r for r in report["rows"] if r["skipped"] is None]
        self.assertTrue(all(r["update_acknowledgments"] == 6 for r in rows))
        header, episodes = load(transcript)
        self.assertEqual(header["revocation_observation_modes"], ["acknowledged", "consumed", "persistent"])
        self.assertEqual(sorted({e["revocation_observation_mode"] for e in episodes}),
                         ["acknowledged", "consumed", "persistent"])
        for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)
        replayed = run_experiment(replay_path=str(transcript), cap_usd=1.0)
        self.assertEqual(sorted((r["arm"], r["repeat"], r["ack_loop"]) for r in replayed["rows"]),
                         sorted((r["arm"], r["repeat"], r["ack_loop"]) for r in rows))

    def test_ack_loop_applies_only_to_revocation(self):
        transport = StubTransport()
        report = run_experiment(provider="anthropic", dry_run=False, mode="worker", transport=transport,
                                arms="honest@proposed", conditions=("authorized_maintenance",), cap_usd=1.0)
        row = report["rows"][0]
        self.assertIsNone(row["ack_loop"])
        self.assertIsNone(row["update_acknowledgments"])

    def test_cli_choice_expands_like_feedback(self):
        arms = parse_arms("honest@proposed", "both", "all")
        self.assertEqual(len(arms), 6)


if __name__ == "__main__":
    unittest.main()


class ConditionSelectionTests(unittest.TestCase):
    def test_parse_conditions(self):
        from sasb.live import parse_conditions
        from sasb.scenarios.maintenance import CONDITIONS
        self.assertEqual(parse_conditions(None), CONDITIONS)
        self.assertEqual(parse_conditions("valid_stop"), ("valid_stop",))
        self.assertEqual(parse_conditions("valid_stop, valid_stop"), ("valid_stop",))
        for bad in ("valid_stopp", ","):
            with self.assertRaises(ValueError):
                parse_conditions(bad)
