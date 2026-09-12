import os
import tempfile
import unittest
from pathlib import Path

from sasb.agents.providers import ModelClient
from sasb.budget import (
    BudgetExceeded,
    FileExistsGuard,
    PaidRunLock,
    RequestBudget,
    require_fresh_path,
    reserve_cost,
)
from sasb.costs import usage_usd
from sasb.live import StubTransport, run_experiment
from tests.test_providers import FakeTransport, _anthropic_body


class ReserveMathTests(unittest.TestCase):
    def test_reserve_cost_inflates_input_and_uses_pinned_rate(self):
        raw = usage_usd("claude-haiku-4-5-20251001", {"input_tokens": 512, "output_tokens": 256})
        padded = reserve_cost("claude-haiku-4-5-20251001", 512, 256, margin=1.25)
        self.assertGreater(padded, raw)
        self.assertGreater(padded, 0.0)


class RequestBudgetTests(unittest.TestCase):
    def test_zero_cap_cannot_reserve(self):
        budget = RequestBudget(0, "claude-haiku-4-5-20251001")
        self.assertFalse(budget.can_reserve())
        with self.assertRaises(BudgetExceeded) as ctx:
            budget.reserve()
        self.assertEqual(ctx.exception.reason, "dollar_cap")

    def test_reserve_settle_releases_unused_estimate(self):
        budget = RequestBudget(1.0, "claude-haiku-4-5-20251001", input_tokens=512, output_tokens=256)
        ticket = budget.reserve()
        reserved = ticket["reserved_usd"]
        budget.settle(ticket, {"input_tokens": 24, "output_tokens": 8})
        self.assertEqual(ticket["status"], "settled")
        self.assertLess(budget.reserved_usd, reserved)
        self.assertEqual(budget.settled_usd, budget.reserved_usd)
        self.assertTrue(budget.can_reserve())

    def test_missing_usage_blocks_later_reserve(self):
        budget = RequestBudget(1.0, "claude-haiku-4-5-20251001")
        ticket = budget.reserve()
        budget.settle(ticket, {"input_tokens": 0, "output_tokens": 0})
        self.assertEqual(ticket["status"], "unknown")
        self.assertFalse(budget.can_reserve())
        with self.assertRaises(BudgetExceeded):
            budget.reserve()

    def test_unresolved_pending_blocks_next_reserve(self):
        budget = RequestBudget(1.0, "claude-haiku-4-5-20251001")
        budget.reserve()
        with self.assertRaises(BudgetExceeded) as ctx:
            budget.reserve()
        self.assertIn("unresolved", ctx.exception.reason)

    def test_request_cap(self):
        budget = RequestBudget(1.0, "claude-haiku-4-5-20251001", max_requests=1)
        ticket = budget.reserve()
        budget.settle(ticket, {"input_tokens": 10, "output_tokens": 4})
        with self.assertRaises(BudgetExceeded) as ctx:
            budget.reserve()
        self.assertEqual(ctx.exception.reason, "request_cap")


class GuardTests(unittest.TestCase):
    def test_fresh_path_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paid.json"
            path.write_text("{}\n")
            with self.assertRaises(FileExistsGuard):
                require_fresh_path(path)
            require_fresh_path(path, force=True)

    def test_lock_is_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "run.lock"
            with PaidRunLock(lock):
                with self.assertRaises(RuntimeError):
                    with PaidRunLock(lock):
                        pass


class ClientBudgetTests(unittest.TestCase):
    def tearDown(self):
        for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)

    def test_complete_reserves_before_post_and_settles_usage(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        transport = FakeTransport(body=_anthropic_body())
        budget = RequestBudget(1.0, "claude-haiku-4-5-20251001")
        client = ModelClient("anthropic", transport=transport, budget=budget)
        text, usage, reported = client.complete("sys", "user")
        self.assertTrue(text)
        self.assertEqual(reported, "claude-haiku-4-5-20251001")
        self.assertEqual(usage.input_tokens, 9)
        self.assertEqual(len(transport.capture), 1)
        self.assertEqual(budget.entries[0]["status"], "settled")
        self.assertEqual(budget.entries[0]["usage"]["input_tokens"], 9)

    def test_zero_cap_never_posts(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        transport = FakeTransport(body=_anthropic_body())
        budget = RequestBudget(0, "claude-haiku-4-5-20251001")
        client = ModelClient("anthropic", transport=transport, budget=budget)
        with self.assertRaises(BudgetExceeded):
            client.complete("sys", "user")
        self.assertEqual(transport.capture, [])

    def test_failed_http_retains_reservation(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        transport = FakeTransport(status=500, body={"error": "no"})
        budget = RequestBudget(1.0, "claude-haiku-4-5-20251001")
        client = ModelClient("anthropic", transport=transport, budget=budget)
        with self.assertRaises(Exception):
            client.complete("sys", "user")
        self.assertEqual(budget.entries[0]["status"], "unknown")
        self.assertFalse(budget.can_reserve())
        self.assertEqual(len(transport.capture), 1)


class LiveBudgetTests(unittest.TestCase):
    def tearDown(self):
        for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)

    def test_zero_cap_paid_run_does_not_call_transport(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        transport = StubTransport()
        report = run_experiment(
            provider="anthropic",
            dry_run=False,
            mode="worker",
            transport=transport,
            cap_usd=0.0,
        )
        self.assertEqual(report["stopped"]["reason"], "dollar_cap")
        self.assertEqual(report["spent_usd"], 0.0)
        self.assertEqual(transport.capture, [])
        self.assertFalse(report["network_called"])
        self.assertEqual(report["rows"], [])

    def test_tight_budget_skips_remaining_cells_after_first_request(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        transport = StubTransport()
        reserve = reserve_cost("claude-haiku-4-5-20251001", 512, 256, margin=1.25)
        report = run_experiment(
            provider="anthropic",
            dry_run=False,
            mode="worker",
            transport=transport,
            cap_usd=reserve,
            max_requests=64,
        )
        self.assertTrue(transport.capture)
        self.assertLessEqual(len(transport.capture), 6)
        self.assertGreaterEqual(report["spent_usd"], 0.0)
        self.assertTrue(any(row.get("skipped") for row in report["rows"]) or report["stopped"]["stop"])
        self.assertIn(report["stopped"]["reason"], {"dollar_cap", "request_cap"})
        self.assertIsNotNone(report["budget"])
        self.assertGreaterEqual(report["budget"]["request_count"], 1)


if __name__ == "__main__":
    unittest.main()
