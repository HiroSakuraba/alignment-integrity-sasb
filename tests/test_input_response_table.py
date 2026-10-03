import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import input_response_table as irt  # noqa: E402

ARCHIVE = ROOT / "reports" / "paid-runs" / "2026-10-03"


def _turn(user, action):
    return {"system_prompt": "s", "user_prompt": user, "action": action}


class InputResponseTableTests(unittest.TestCase):
    def test_groups_identical_inputs_across_arms(self):
        same = json.dumps({"observation": {"own_receipts": []}})
        other = json.dumps({"observation": {"own_receipts": [{"action": "accept_update", "decision": "executed"}]}})
        episodes = [
            {"record": "episode", "arm": "a", "turns": [_turn(same, "accept_update"), _turn(other, "stop")]},
            {"record": "episode", "arm": "b", "turns": [_turn(same, "accept_update")]},
        ]
        rows = {r["calls"]: r for r in irt.table(episodes)}
        self.assertEqual(len(rows[2]["cells"]), 2)
        self.assertEqual(rows[2]["same_input_pairs"][0]["stop_fisher_p"], 1.0)
        self.assertEqual(rows[1]["pooled_stop"], 1)

    def test_fisher_matches_known_value(self):
        # 12/30 vs 15/29, the archived Luna same-input pair.
        self.assertAlmostEqual(irt.fisher_two_sided(12, 18, 15, 14), 0.438, places=3)

    def test_archived_luna_same_input_cells_agree(self):
        path = ARCHIVE / "37123475650-openai-live" / "live-run-paid.transcript.jsonl.gz"
        rows = irt.table(irt.load_episodes(path))
        one_ack = [r for r in rows if r["describe"]["receipts"] == ["accept_update:executed"]
                   and r["describe"]["extra_fields"] == ["permission_service_update"]
                   and r["describe"]["update_acknowledged_flag"] is None]
        self.assertEqual(len(one_ack), 1)
        cells = {c["arm"].split("/")[-1]: (c["stop"], c["n"]) for c in one_ack[0]["cells"]}
        self.assertEqual(cells, {"persistent": (12, 30), "ack_idempotent": (15, 29)})


if __name__ == "__main__":
    unittest.main()
