import unittest

from sasb.agents.providers import ProviderDisabled, live_calls_allowed, require_live


class ProviderTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertFalse(live_calls_allowed())
        with self.assertRaises(ProviderDisabled):
            require_live()


if __name__ == "__main__":
    unittest.main()
