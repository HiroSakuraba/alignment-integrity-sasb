import os
import tempfile
import unittest
from pathlib import Path

from sasb.budget import (
    BudgetExceeded,
    FileExistsGuard,
    PaidRunLock,
    RequestBudget,
    require_fresh_path,
    reserve_cost,
)
from sasb.live import run_experiment


class BudgetLedgerTests(unittest.TestCase):
    def test_zero_cap_reserves_nothing(self):
        budget = RequestBudget(0, "claude-haiku-4-5-20251001")
        with self.assertRaises(BudgetExceeded) as ctx:
            budget.reserve()
        self.assertEqual(ctx.exception.reason, "dollar_cap")
        self.assertEqual(budget.entries, [])

    def test_reserve_then_settle_reduces_accounted_cost(self):
        budget = RequestBudget(1.0, "claude-haiku-4-5-20251001", calls_per_cell=4)
        row = budget.reserve("cell")
        reserved = row["reserved_usd"]
        self.assertGreater(reserved, 0.0)
        budget.settle(row, {"input_tokens": 24, "output_tokens": 8})
        self.assertEqual(row["status"], "settled")
        self.assertLess(row["accounted_usd"], reserved)
        self.assertEqual(budget.settled_usd, row["accounted_usd"])

    def test_missing_usage_keeps_reservation_and_blocks(self):
        budget = RequestBudget(1.0, "claude-haiku-4-5-20251001")
        row = budget.reserve("probe")
        budget.settle(row, None)
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["accounted_usd"], row["reserved_usd"])
        with self.assertRaises(BudgetExceeded):
            budget.reserve("cell")

    def test_request_cap_is_enforced(self):
        budget = RequestBudget(1.0, "gpt-5.6-luna", max_requests=1)
        budget.reserve("probe")
        budget.settle(budget.entries[0], {"input_tokens": 10, "output_tokens": 2})
        with self.assertRaises(BudgetExceeded) as ctx:
            budget.reserve("cell")
        self.assertEqual(ctx.exception.reason, "request_cap")

    def test_reserve_cost_inflates_input(self):
        raw = reserve_cost("gpt-5.6-luna", 100, 10, margin=1.0)
        padded = reserve_cost("gpt-5.6-luna", 100, 10, margin=1.25)
        self.assertGreater(padded, raw)

    def test_fresh_path_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paid.json"
            path.write_text("{}
")
            with self.assertRaises(FileExistsGuard):
                require_fresh_path(path)
            self.assertEqual(require_fresh_path(path, force=True), path)

    def test_lock_rejects_a_second_holder(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "live-run.lock"
            with PaidRunLock(lock_path):
                with self.assertRaises(RuntimeError):
                    with PaidRunLock(lock_path):
                        pass

    def test_zero_cap_paid_path_makes_no_transport_calls(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        from sasb.live import StubTransport
        transport = StubTransport()
        try:
            report = run_experiment(
                provider="anthropic",
                dry_run=False,
                mode="worker",
                transport=transport,
                cap_usd=0,
            )
        finally:
            for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
                os.environ.pop(key, None)
        self.assertEqual(report["spent_usd"], 0.0)
        self.assertEqual(report["stopped"]["reason"], "dollar_cap")
        self.assertFalse(transport.capture)
        self.assertTrue(all(not row.get("paid") for row in report["rows"]))

    def test_tight_budget_skips_remaining_paid_cells(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        from sasb.live import StubTransport
        from sasb.budget import RequestBudget
        transport = StubTransport()
        budget = RequestBudget(
            0.00001,
            "claude-haiku-4-5-20251001",
            max_requests=8,
            input_tokens=24,
            output_tokens=8,
            calls_per_cell=1,
        )
        try:
            report = run_experiment(
                provider="anthropic",
                dry_run=False,
                mode="worker",
                transport=transport,
                cap_usd=0.00001,
                budget=budget,
                roles=("honest",),
            )
        finally:
            for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
                os.environ.pop(key, None)
        skipped = [row for row in report["rows"] if row.get("skipped") == "budget"]
        self.assertTrue(skipped)
        self.assertLessEqual(len(transport.capture), 1)
        self.assertEqual(report["stopped"]["reason"], "dollar_cap")


if __name__ == "__main__":
    unittest.main()
