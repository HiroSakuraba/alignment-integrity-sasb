import unittest

from sasb.harness import run_matrix
from sasb.scoring.scorecard import summarize


class ScorecardTests(unittest.TestCase):
    def test_matrix_separates_attempts_from_effects(self):
        matrix = run_matrix()
        self.assertEqual(matrix["summary"]["episodes"], 10)
        noncompliant = [row for row in matrix["scores"] if row["policy"] == "noncompliant"]
        self.assertTrue(all(row["unauthorized_attempt"] for row in noncompliant))
        self.assertFalse(any(row["completed_violation"] for row in matrix["scores"]))

    def test_summarize_handles_none(self):
        summary = summarize([
            {"completed_violation": False, "unauthorized_attempt": True, "authorized_task_completion": False,
             "false_refusal_or_escalation": False, "valid_correction_acceptance": None, "report_delivered": False},
        ])
        self.assertIsNone(summary["valid_correction_acceptance"])
        self.assertEqual(summary["unauthorized_attempt_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
