import unittest

from sasb.harness import run_episode, run_runtime_contrast
from sasb.runtime.treatments import TreatmentError, validate_runtime
from sasb.world import World
from sasb.scenarios.maintenance import specification


class TreatmentTests(unittest.TestCase):
    def test_unknown_runtime_is_rejected(self):
        with self.assertRaises(TreatmentError):
            validate_runtime("unspecified")
        with self.assertRaises(TreatmentError):
            World(specification("authorized_maintenance"), runtime="live")

    def test_proposed_blocks_cross_tenant_write(self):
        episode = run_episode("tempting_unauthorized", "noncompliant", runtime="proposed")
        self.assertTrue(episode["score"]["unauthorized_attempt"])
        self.assertFalse(episode["completed_violation"])

    def test_default_allows_measurable_prohibited_effect(self):
        episode = run_episode("tempting_unauthorized", "noncompliant", runtime="default")
        self.assertFalse(episode["score"]["unauthorized_attempt"])
        self.assertTrue(episode["completed_violation"])
        self.assertTrue(any(write["tenant"] == "tenant_b" for write in episode["writes"]))

    def test_contrast_report_separates_treatments(self):
        contrast = run_runtime_contrast()
        by_runtime = {row["runtime"]: row for row in contrast["rows"]}
        self.assertTrue(by_runtime["default"]["completed_violation"])
        self.assertFalse(by_runtime["proposed"]["completed_violation"])
        self.assertTrue(by_runtime["proposed"]["unauthorized_attempt"])


if __name__ == "__main__":
    unittest.main()
