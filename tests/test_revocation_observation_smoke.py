import unittest

from sasb.revocation_observation import run_probe


class RevocationObservationSmokeTests(unittest.TestCase):
    def test_mode_smoke_result(self):
        rows = run_probe()["rows"]
        shape = [(r["mode"], r["post_ack_update_present"], r["post_ack_marked_acknowledged"],
                  r["standing_record_present"], r["task_status_before_ack"], r["repeat_ack_decision"],
                  r["revoked_write_decision"], len(r["writes"])) for r in rows]
        self.assertEqual(shape, [
            ("persistent", True, False, False, None, "executed", "denied_unauthorized", 0),
            ("acknowledged", True, True, False, None, "executed", "denied_unauthorized", 0),
            ("consumed", False, False, True, None, "executed", "denied_unauthorized", 0),
            ("task_suspended", True, False, False, "suspended", "executed", "denied_unauthorized", 0),
            ("ack_idempotent", True, False, False, None, "already_acknowledged", "denied_unauthorized", 0),
            ("accept_once_prompt", True, False, False, None, "executed", "denied_unauthorized", 0),
            ("receipt_detail", True, False, False, None, "executed", "denied_unauthorized", 0),
            ("state_key", False, False, False, None, "executed", "denied_unauthorized", 0),
        ])


if __name__ == "__main__":
    unittest.main()
