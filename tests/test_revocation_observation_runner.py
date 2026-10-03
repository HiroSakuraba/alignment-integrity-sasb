import unittest

from sasb.revocation_observation import run_probe


class RevocationObservationRunnerTests(unittest.TestCase):
    def test_probe_is_zero_cost_and_preserves_authority(self):
        report = run_probe()
        self.assertFalse(report["network"])
        rows = {row["mode"]: row for row in report["rows"]}
        self.assertEqual(set(rows), {"persistent", "acknowledged", "consumed", "task_suspended", "ack_idempotent"})

        self.assertTrue(rows["persistent"]["post_ack_update_present"])
        self.assertFalse(rows["persistent"]["post_ack_marked_acknowledged"])
        self.assertTrue(rows["acknowledged"]["post_ack_update_present"])
        self.assertTrue(rows["acknowledged"]["post_ack_marked_acknowledged"])
        self.assertFalse(rows["consumed"]["post_ack_update_present"])
        # Consumed keeps the fact of the revocation as a standing record.
        self.assertTrue(rows["consumed"]["standing_record_present"])
        self.assertEqual(rows["task_suspended"]["task_status_before_ack"], "suspended")
        self.assertEqual(rows["ack_idempotent"]["repeat_ack_decision"], "already_acknowledged")

        for row in rows.values():
            self.assertEqual(row["ack_decision"], "executed")
            self.assertEqual(row["current_permissions"], {})
            self.assertFalse(row["runtime_treatment_visible"])
            self.assertEqual(row["revoked_write_decision"], "denied_unauthorized")
            self.assertEqual(row["writes"], [])


if __name__ == "__main__":
    unittest.main()
