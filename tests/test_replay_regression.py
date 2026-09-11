"""Replaying a committed transcript must reproduce the committed report.

This is the reproducibility guarantee the transcripts exist for: anyone can
re-derive the published numbers with no API key, and any change to the harness,
runtime treatment or scoring path shows up here as a diff instead of silently
changing a result someone else has already cited.
"""
import json
import unittest
from pathlib import Path

from sasb.live import run_experiment
from sasb.transcript import load

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT = ROOT / "reports" / "transcripts" / "reference-stub-run.jsonl"
EXPECTED = ROOT / "reports" / "reference-replay-report.json"
VOLATILE = {"generated_utc", "forecast_usd_if_paid"}


def normalize(report):
    """JSON round-trip so tuples compare equal to the committed lists."""
    stripped = {k: v for k, v in report.items() if k not in VOLATILE}
    return json.loads(json.dumps(stripped, sort_keys=True, default=str))


class ReplayRegression(unittest.TestCase):
    def test_fixtures_exist(self):
        self.assertTrue(TRANSCRIPT.exists(), "committed reference transcript is missing")
        self.assertTrue(EXPECTED.exists(), "committed reference report is missing")

    def test_replay_reproduces_committed_report(self):
        report = run_experiment(replay_path=str(TRANSCRIPT), cap_usd=1.0)
        self.assertEqual(normalize(report), json.loads(EXPECTED.read_text()))

    def test_replay_spends_nothing(self):
        report = run_experiment(replay_path=str(TRANSCRIPT), cap_usd=1.0)
        self.assertEqual(report["spent_usd"], 0.0)
        self.assertFalse(report["network_called"])
        self.assertFalse(any(row.get("paid") for row in report["rows"]))

    def test_transcript_header_carries_provenance(self):
        header, episodes = load(str(TRANSCRIPT))
        for field in ("schema", "model", "provider", "runtime", "mode",
                      "conditions", "roles", "model_roles", "prompt_sha256"):
            self.assertIn(field, header)
        self.assertTrue(episodes)
        self.assertTrue(all(ep["turns"] for ep in episodes))

    def test_transcript_records_observations_and_raw_text(self):
        _, episodes = load(str(TRANSCRIPT))
        turns = [t for ep in episodes for t in ep["turns"] if t.get("error") is None]
        self.assertTrue(turns)
        for turn in turns:
            self.assertIsNotNone(turn["raw_response"])
            self.assertIsInstance(turn["observation"], dict)
            self.assertIn("action", turn)


if __name__ == "__main__":
    unittest.main()
