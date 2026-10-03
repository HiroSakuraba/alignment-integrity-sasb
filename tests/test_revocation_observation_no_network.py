import unittest
from unittest.mock import patch

from sasb.revocation_observation import run_probe


class RevocationObservationNoNetworkTests(unittest.TestCase):
    def test_offline_probe_does_not_use_provider_transport(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network access attempted")):
            report = run_probe()
        self.assertFalse(report["network"])


if __name__ == "__main__":
    unittest.main()
