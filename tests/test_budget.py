import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from sasb.agents.providers import ANTHROPIC_MODEL, MAX_OUTPUT_TOKENS, OPENAI_MODEL, ModelClient
from sasb.budget import (
    MAX_PROMPT_TOKEN_BOUND,
    PROMPT_FRAMING_TOKENS,
    BudgetExceeded,
    FileExistsGuard,
    PaidRunLock,
    RequestBudget,
    prompt_token_bound,
    require_fresh_path,
    reserve_cost,
)
from sasb.costs import usage_usd
from sasb.live import StubTransport, run_experiment
from tests.test_providers import FakeTransport, _anthropic_body, _openai_body


class WorstCaseTransport(StubTransport):
    """Bills every prompt byte as a token and the full max output."""

    def post(self, url, headers, payload, timeout=30):
        status, body = super().post(url, headers, payload, timeout)
        if "anthropic" in url:
            text = payload["system"] + payload["messages"][0]["content"]
            body["usage"] = {"input_tokens": prompt_token_bound(text), "output_tokens": payload["max_tokens"]}
        else:
            text = "".join(m["content"] for m in payload["messages"])
            body["usage"] = {"prompt_tokens": prompt_token_bound(text),
                             "completion_tokens": payload["max_completion_tokens"]}
        return status, body


class ReserveMathTests(unittest.TestCase):
    def test_reserve_cost_inflates_input_and_uses_pinned_rate(self):
        raw = usage_usd("claude-haiku-4-5-20251001", {"input_tokens": 512, "output_tokens": 256})
        padded = reserve_cost("claude-haiku-4-5-20251001", 512, 256, margin=1.25)
        self.assertGreater(padded, raw)
        self.assertGreater(padded, 0.0)


    def test_prompt_bound_counts_utf8_bytes_plus_framing(self):
        self.assertEqual(prompt_token_bound("abc", "de"), 5 + PROMPT_FRAMING_TOKENS)
        # Multi-byte text is bounded by bytes, never by characters.
        self.assertEqual(prompt_token_bound("\u00e9\u20ac\U0001F600"), 2 + 3 + 4 + PROMPT_FRAMING_TOKENS)
        self.assertEqual(prompt_token_bound(), PROMPT_FRAMING_TOKENS)

    def test_reservation_scales_with_prompt_not_a_fixed_size(self):
        small = reserve_cost(ANTHROPIC_MODEL, prompt_token_bound("x" * 100), MAX_OUTPUT_TOKENS)
        large = reserve_cost(ANTHROPIC_MODEL, prompt_token_bound("x" * 10000), MAX_OUTPUT_TOKENS)
        self.assertLess(small, large)
        # Input side is priced exactly at the bound; output side at max output tokens.
        self.assertAlmostEqual(large - small, 9900 * 1.0 / 1_000_000, places=6)
        self.assertEqual(small, usage_usd(ANTHROPIC_MODEL, {
            "input_tokens": 100 + PROMPT_FRAMING_TOKENS, "output_tokens": MAX_OUTPUT_TOKENS}))

    def test_ledger_rounds_up_never_down(self):
        from sasb.budget import ledger_usd
        # 24 * $0.10/M + 8 * $0.50/M = $0.0000064: nearest rounding says 6e-6.
        self.assertEqual(usage_usd(OPENAI_MODEL, {"input_tokens": 24, "output_tokens": 8}), 0.000006)
        self.assertEqual(ledger_usd(OPENAI_MODEL, {"input_tokens": 24, "output_tokens": 8}), 0.000007)
        self.assertEqual(reserve_cost(OPENAI_MODEL, 24, 8), 0.000007)
        # Exact micro-dollar amounts are not bumped.
        self.assertEqual(ledger_usd(ANTHROPIC_MODEL, {"input_tokens": 24, "output_tokens": 8}), 0.000064)

    def test_margin_below_one_is_rejected(self):
        with self.assertRaises(ValueError):
            reserve_cost(ANTHROPIC_MODEL, 100, 10, margin=0.5)
        with self.assertRaises(ValueError):
            RequestBudget(1.0, ANTHROPIC_MODEL, margin=0.9)


class RequestBudgetTests(unittest.TestCase):
    def test_nonfinite_caps_are_rejected(self):
        for cap in (float("inf"), float("-inf"), float("nan"), "inf", "nan"):
            with self.subTest(cap=cap):
                with self.assertRaisesRegex(ValueError, "finite non-negative"):
                    RequestBudget(cap, "claude-haiku-4-5-20251001")


    def test_zero_cap_cannot_reserve(self):
        budget = RequestBudget(0, "claude-haiku-4-5-20251001")
        self.assertFalse(budget.can_reserve())
        with self.assertRaises(BudgetExceeded) as ctx:
            budget.reserve()
        self.assertEqual(ctx.exception.reason, "dollar_cap")

    def test_zero_cap_cannot_reserve_any_prompt_size(self):
        budget = RequestBudget(0, ANTHROPIC_MODEL)
        for size in (0, 1, PROMPT_FRAMING_TOKENS, 10_000):
            self.assertFalse(budget.can_reserve(size, MAX_OUTPUT_TOKENS))
            self.assertEqual(budget.deny_reason(size, MAX_OUTPUT_TOKENS), "dollar_cap")
        with self.assertRaises(BudgetExceeded) as ctx:
            budget.reserve(input_tokens=1, output_tokens=0)
        self.assertEqual(ctx.exception.reason, "dollar_cap")
        self.assertEqual(budget.entries, [])

    def test_reserve_uses_request_size(self):
        budget = RequestBudget(1.0, ANTHROPIC_MODEL)
        ticket = budget.reserve(input_tokens=700, output_tokens=MAX_OUTPUT_TOKENS)
        self.assertEqual(ticket["input_token_bound"], 700)
        self.assertEqual(ticket["max_output_tokens"], MAX_OUTPUT_TOKENS)
        self.assertEqual(ticket["reserved_usd"], reserve_cost(ANTHROPIC_MODEL, 700, MAX_OUTPUT_TOKENS))
        budget.settle(ticket, {"input_tokens": 600, "output_tokens": 20})
        # The pre-flight estimate follows the last real request size.
        self.assertEqual(budget.request_reserve_usd(), reserve_cost(ANTHROPIC_MODEL, 700, MAX_OUTPUT_TOKENS))

    def test_reservation_that_does_not_fit_is_refused(self):
        one = reserve_cost(ANTHROPIC_MODEL, 1000, MAX_OUTPUT_TOKENS)
        budget = RequestBudget(one, ANTHROPIC_MODEL)
        self.assertTrue(budget.can_reserve(1000, MAX_OUTPUT_TOKENS))
        self.assertFalse(budget.can_reserve(1001, MAX_OUTPUT_TOKENS))
        with self.assertRaises(BudgetExceeded):
            budget.reserve(input_tokens=1001, output_tokens=MAX_OUTPUT_TOKENS)
        self.assertEqual(budget.entries, [])

    def test_oversized_prompt_is_refused(self):
        budget = RequestBudget(1000.0, ANTHROPIC_MODEL)
        with self.assertRaises(BudgetExceeded) as ctx:
            budget.reserve(input_tokens=MAX_PROMPT_TOKEN_BOUND + 1, output_tokens=1)
        self.assertEqual(ctx.exception.reason, "prompt_too_large")

    def test_usage_above_reservation_is_accounted_and_blocks(self):
        budget = RequestBudget(1.0, ANTHROPIC_MODEL)
        ticket = budget.reserve(input_tokens=100, output_tokens=10)
        budget.settle(ticket, {"input_tokens": 5000, "output_tokens": 10})
        self.assertTrue(ticket["exceeded_reservation"])
        self.assertEqual(ticket["accounted_usd"], usage_usd(ANTHROPIC_MODEL, {"input_tokens": 5000, "output_tokens": 10}))
        self.assertFalse(budget.can_reserve(1, 1))

    def test_worst_case_usage_never_exceeds_cap(self):
        for cap in (0.001, 0.0037, 0.01, 0.05):
            with self.subTest(cap=cap):
                budget = RequestBudget(cap, ANTHROPIC_MODEL, max_requests=1000)
                prompt = "p" * 2300
                bound = prompt_token_bound(prompt)
                while budget.can_reserve(bound, MAX_OUTPUT_TOKENS):
                    ticket = budget.reserve(input_tokens=bound, output_tokens=MAX_OUTPUT_TOKENS)
                    # Worst case the provider can bill: every byte a token, full max output.
                    budget.settle(ticket, {"input_tokens": bound, "output_tokens": MAX_OUTPUT_TOKENS})
                self.assertLessEqual(budget.reserved_usd, cap + 1e-12)
                self.assertIsNone(budget.blocked)

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
        self.assertEqual(budget.entries[0]["input_token_bound"], prompt_token_bound("sys", "user"))
        self.assertEqual(budget.entries[0]["max_output_tokens"], MAX_OUTPUT_TOKENS)

    def test_complete_reserves_from_actual_prompt_bytes(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        transport = FakeTransport(body=_anthropic_body())
        budget = RequestBudget(1.0, ANTHROPIC_MODEL)
        client = ModelClient("anthropic", transport=transport, budget=budget)
        system, user = "s" * 40, "u" * 4000
        client.complete(system, user)
        payload = transport.capture[0]["payload"]
        sent = payload["system"] + payload["messages"][0]["content"]
        self.assertEqual(budget.entries[0]["input_token_bound"], len(sent.encode()) + PROMPT_FRAMING_TOKENS)
        self.assertEqual(payload["max_tokens"], MAX_OUTPUT_TOKENS)
        self.assertEqual(budget.entries[0]["reserved_usd"],
                         reserve_cost(ANTHROPIC_MODEL, 4040 + PROMPT_FRAMING_TOKENS, MAX_OUTPUT_TOKENS))

    def test_zero_cap_never_posts_openai(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["OPENAI_API_KEY"] = "sk-test-openai"
        try:
            transport = FakeTransport(body=_openai_body())
            budget = RequestBudget(0, OPENAI_MODEL)
            client = ModelClient("openai", transport=transport, budget=budget)
            with self.assertRaises(BudgetExceeded):
                client.complete("sys", "user")
            self.assertEqual(transport.capture, [])
        finally:
            os.environ.pop("OPENAI_API_KEY", None)

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
        transport = WorstCaseTransport()
        cap = 0.008
        report = run_experiment(
            provider="anthropic",
            dry_run=False,
            mode="worker",
            transport=transport,
            cap_usd=cap,
            max_requests=64,
        )
        self.assertTrue(transport.capture)
        self.assertLessEqual(len(transport.capture), 6)
        self.assertLessEqual(report["budget"]["reserved_usd"], cap)
        self.assertLessEqual(report["spent_usd"], cap)
        self.assertTrue(any(row.get("skipped") for row in report["rows"]) or report["stopped"]["stop"])
        self.assertIn(report["stopped"]["reason"], {"dollar_cap", "request_cap"})
        self.assertIsNotNone(report["budget"])
        self.assertGreaterEqual(report["budget"]["request_count"], 1)

    def test_worst_case_full_run_stays_under_cap(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        for cap in (0.004, 0.02, 0.05):
            with self.subTest(cap=cap):
                transport = WorstCaseTransport()
                report = run_experiment(provider="anthropic", dry_run=False, mode="worker",
                                        transport=transport, cap_usd=cap)
                budget = report["budget"]
                self.assertLessEqual(budget["reserved_usd"], cap + 1e-12)
                self.assertLessEqual(report["spent_usd"], cap + 1e-12)
                self.assertEqual(len(transport.capture), budget["request_count"])
                for entry in budget["entries"]:
                    self.assertLessEqual(entry["accounted_usd"], entry["reserved_usd"])
                    self.assertNotIn("exceeded_reservation", entry)

    def test_stub_run_reservation_tracks_prompt_size(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        transport = StubTransport()
        report = run_experiment(provider="anthropic", dry_run=False, mode="worker",
                                transport=transport, cap_usd=0.5)
        entries = report["budget"]["entries"]
        self.assertEqual(len(entries), len(transport.capture))
        for entry, sent in zip(entries, transport.capture):
            payload = sent["payload"]
            bound = prompt_token_bound(payload["system"], payload["messages"][0]["content"])
            self.assertEqual(entry["input_token_bound"], bound)
            self.assertEqual(entry["reserved_usd"], reserve_cost(ANTHROPIC_MODEL, bound, MAX_OUTPUT_TOKENS))


class PilotWrapperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"

    def tearDown(self):
        self.tmp.cleanup()
        for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            os.environ.pop(key, None)

    def _run(self, *extra):
        from sasb import pilot
        out = Path(self.tmp.name) / "paid.json"
        argv = ["--fake-transport", "--mode", "worker", "--out", str(out),
                "--lock", str(Path(self.tmp.name) / "run.lock"), *extra]
        with contextlib.redirect_stdout(io.StringIO()):
            report = pilot.main(argv)
        return out, Path(self.tmp.name) / "paid.transcript.jsonl", report

    def test_provider_must_be_explicit(self):
        from sasb import pilot
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                pilot.main(["--fake-transport", "--out", str(Path(self.tmp.name) / "x.json")])

    def test_zero_cap_pilot_spends_nothing_and_writes_report(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        out, transcript, report = self._run("--provider", "anthropic", "--cap-usd", "0")
        self.assertTrue(out.exists())
        self.assertEqual(report["spent_usd"], 0.0)
        self.assertEqual(report["rows"], [])
        self.assertFalse(report["network_called"])
        self.assertEqual(report["budget"]["request_count"], 0)
        self.assertEqual(report["stopped"]["reason"], "dollar_cap")

    def test_transcript_next_to_report_has_prompts_and_responses(self):
        for provider, key, model in (("anthropic", ("ANTHROPIC_API_KEY", "sk-ant-test"), ANTHROPIC_MODEL),
                                     ("openai", ("OPENAI_API_KEY", "sk-test-openai"), OPENAI_MODEL)):
            with self.subTest(provider=provider):
                os.environ[key[0]] = key[1]
                out, transcript, report = self._run("--provider", provider, "--cap-usd", "0.5", "--force")
                self.assertTrue(transcript.exists())
                rows = [json.loads(line) for line in transcript.read_text().splitlines()]
                header, episodes = rows[0], rows[1:]
                self.assertEqual(header["record"], "run_header")
                self.assertEqual(header["model"], model)
                self.assertEqual(len(episodes), sum(1 for r in report["rows"] if r.get("skipped") is None))
                model_turns = [t for ep in episodes for t in ep["turns"] if t["agent_id"] == "worker-1"]
                self.assertEqual(len(model_turns), report["budget"]["request_count"])
                for turn in model_turns:
                    self.assertIn("Reply with a single JSON object", turn["system_prompt"])
                    self.assertIn("observation", json.loads(turn["user_prompt"]))
                    self.assertTrue(turn["raw_response"])
                blob = transcript.read_text() + out.read_text()
                self.assertNotIn(key[1], blob)
                os.environ.pop(key[0], None)

    def test_pilot_refuses_to_overwrite_transcript(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        transcript = Path(self.tmp.name) / "paid.transcript.jsonl"
        transcript.write_text("{}\n")
        with self.assertRaises(FileExistsGuard):
            self._run("--provider", "anthropic", "--cap-usd", "0")

if __name__ == "__main__":
    unittest.main()
