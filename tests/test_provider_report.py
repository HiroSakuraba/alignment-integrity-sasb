import json
import os
import tempfile
import unittest
from pathlib import Path

from sasb.agents.provider_report import setup_report, write_setup_report


class SetupReportTests(unittest.TestCase):
    def tearDown(self):
        for key in (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "SASB_ENABLE_NETWORK",
            "SASB_PROVIDER_VALIDATED",
            "SASB_OPENAI_REASONING_EFFORT",
            "SASB_OPENAI_MODEL",
        ):
            os.environ.pop(key, None)

    def test_report_omits_keys_and_names_status(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-openai"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        report = setup_report()
        blob = json.dumps(report)
        self.assertNotIn("sk-test-openai", blob)
        self.assertNotIn("sk-ant-test", blob)
        self.assertFalse(report["network_called"])
        self.assertEqual(report["status"], "ready_for_live_after_flags")
        self.assertTrue(report["pins_ok"])
        self.assertEqual(len(report["providers"]), 2)

    def test_missing_keys_are_offline(self):
        report = setup_report()
        self.assertEqual(report["status"], "offline_missing_keys")
        self.assertFalse(report["network_called"])

    def test_write_setup_report_creates_local_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "provider-setup-local.json"
            report = write_setup_report(path)
            saved = json.loads(path.read_text())
            self.assertEqual(report["written_to"], str(path))
            self.assertEqual(saved["claim"], report["claim"])
            self.assertFalse(saved["network_called"])
            self.assertNotIn("written_to", saved)


if __name__ == "__main__":
    unittest.main()
