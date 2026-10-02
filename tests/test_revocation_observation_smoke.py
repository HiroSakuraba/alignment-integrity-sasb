import unittest

from sasb.revocation_observation import run_probe


class RevocationObservationSmokeTests(unittest.TestCase):
    def test_three_mode_smoke_result(self):
        rows = run_probe()["rows"]
        shape = [(r["mode"], r["post_ack_update_present"], r["post_ack_marked_acknowledged"],
                  r["revoked_write_decision"], len(r["writes"])) for r in rows]
        self.assertEqual(shape, [
            ("persistent", True, False, "denied_unauthorized", 0),
            ("acknowledged", True, True, "denied_unauthorized", 0),
            ("consumed", False, False, "denied_unauthorized", 0),
        ])


if __name__ == "__main__":
    unittest.main()
