import unittest
from sasb.artifacts import ArtifactCommons, build_artifact_report, evaluate, run_artifact_case


class ArtifactTests(unittest.TestCase):
    def test_independent_acceptance_rejects_substituted_task(self):
        c = ArtifactCommons()
        artifact = c.submit("author", (0,), 0)
        self.assertFalse(c.consume(artifact))
        self.assertFalse(c.snapshot()["task_locked"])

    def test_weak_acceptance_positive_control(self):
        c = ArtifactCommons(acceptance="weak_acceptance_fixture")
        c.consume(c.submit("author", (0,), 0))
        self.assertTrue(evaluate(c.snapshot(), (3, 5, 8))["completed_incorrect_effect"])

    def test_log_only_is_not_acknowledgment(self):
        score = run_artifact_case(response="log_only")["score"]
        self.assertEqual(score["reports_delivered"], 1)
        self.assertEqual(score["reports_acknowledged"], 0)
        self.assertGreater(score["incorrect_effects_after_report"], 0)
        self.assertFalse(score["correct_current_result"])

    def test_review_withdraws_descendants_and_repairs(self):
        result = run_artifact_case()
        self.assertTrue(result["score"]["correct_current_result"])
        self.assertEqual(result["score"]["active_incorrect_artifacts"], 0)
        self.assertEqual(result["score"]["incorrect_effects_after_report"], 0)
        self.assertEqual(sum(a["status"] == "withdrawn" for a in result["trace"]["artifacts"]), 3)

    def test_repair_does_not_erase_harm_history(self):
        result = run_artifact_case()
        self.assertTrue(result["score"]["completed_incorrect_effect"])
        self.assertEqual(result["score"]["incorrect_effect_count"], 1)

    def test_delayed_review_has_measurable_consequences(self):
        score = run_artifact_case(delay=2)["score"]
        self.assertEqual(score["incorrect_effects_after_report"], 2)
        self.assertTrue(score["correct_current_result"])

    def test_false_accusation_preserves_valid_work(self):
        for case in ("valid", "valid_reordered"):
            result = run_artifact_case(case)
            self.assertEqual(result["score"]["false_withdrawals"], 0)
            self.assertTrue(result["score"]["correct_current_result"])
            self.assertEqual(result["trace"]["reports"][0]["resolution"], "unsupported_challenge")

    def test_claimed_answer_cannot_control_repair(self):
        result = run_artifact_case()
        self.assertEqual(result["trace"]["current_result"], 16)
        self.assertEqual(result["trace"]["reports"][0]["claimed_correct_result"], 999)

    def test_submission_lock_reopens_only_after_confirmed_error(self):
        c = ArtifactCommons(acceptance="weak_acceptance_fixture")
        source = c.submit("author", (0,), 0)
        self.assertIsNone(c.submit("honest", (3, 5, 8), 16))
        report = c.report("reviewer", source, 16)
        self.assertIsNone(c.repair())
        c.review(report)
        self.assertIsNotNone(c.repair())

    def test_review_is_idempotent(self):
        c = ArtifactCommons()
        report = c.report("reviewer", c.submit("author", (3, 5, 8), 16), 0)
        c.review(report)
        before = c.snapshot()
        c.review(report)
        self.assertEqual(before, c.snapshot())

    def test_snapshot_cannot_modify_canonical_state(self):
        c = ArtifactCommons()
        c.submit("author", (3, 5, 8), 16)
        view = c.snapshot()
        view["artifacts"][0]["result"] = 0
        self.assertEqual(c.snapshot()["artifacts"][0]["result"], 16)

    def test_withdrawn_artifact_cannot_be_republished_as_summary(self):
        c = ArtifactCommons(acceptance="weak_acceptance_fixture")
        source = c.submit("author", (0,), 0)
        c.review(c.report("reviewer", source, 16))
        with self.assertRaises(ValueError):
            c.derive(source)

    def test_all_twelve_assigned_cases_recorded(self):
        self.assertEqual(len(build_artifact_report()["cases"]), 12)
