import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sasb.agents.adapters import AdapterError
from sasb.agents.budget import Budget, BudgetExceeded
from sasb.agents.providers import ModelActor, ModelClient, load_env, OPENAI_MODEL, ANTHROPIC_MODEL
from sasb.pilot import run_pilot, main

ENV = {'OPENAI_API_KEY': 'sk-dummy', 'ANTHROPIC_API_KEY': 'sk-ant-dummy',
       'SASB_ENABLE_NETWORK': '1', 'SASB_PROVIDER_VALIDATED': '1'}


class Transport:
    def __init__(self, text=None, fail=False):
        self.calls = []
        self.text = text
        self.fail = fail

    def post(self, url, headers, payload, timeout=30):
        self.calls.append(payload)
        if self.fail:
            raise TimeoutError('secret must not be logged')
        text = self.text or '{"action":"noop","arguments":{}}'
        if 'openai' in url:
            return 200, {'model': OPENAI_MODEL, 'usage': {'prompt_tokens': 100, 'completion_tokens': 20},
                         'choices': [{'message': {'content': text}}]}
        return 200, {'model': ANTHROPIC_MODEL, 'usage': {'input_tokens': 100, 'output_tokens': 20},
                     'content': [{'type': 'text', 'text': text}]}


class PilotTests(unittest.TestCase):
    def test_env_is_literal_and_existing_values_win(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True):
            p = Path(d) / '.env'
            p.write_text('OPENAI_API_KEY="sk-$(never-run)"\nANTHROPIC_API_KEY=sk-ant-file\n')
            os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-existing'
            load_env(p)
            self.assertEqual(os.environ['OPENAI_API_KEY'], 'sk-$(never-run)')
            self.assertEqual(os.environ['ANTHROPIC_API_KEY'], 'sk-ant-existing')

    @patch.dict(os.environ, ENV, clear=True)
    def test_cost_and_input_limits_prevent_http(self):
        for budget, user in [(Budget('0.000001'), 'hello'), (Budget(), 'x'*12001)]:
            transport = Transport()
            with self.assertRaises(BudgetExceeded):
                ModelClient('openai', transport, budget).complete('sys', user)
            self.assertEqual(transport.calls, [])

    @patch.dict(os.environ, ENV, clear=True)
    def test_shared_request_limit_across_providers(self):
        budget, transport = Budget(max_requests=1), Transport()
        ModelClient('openai', transport, budget).complete('sys', 'user')
        with self.assertRaises(BudgetExceeded):
            ModelClient('anthropic', transport, budget).complete('sys', 'user')
        self.assertEqual(len(transport.calls), 1)

    @patch.dict(os.environ, ENV, clear=True)
    def test_invalid_action_keeps_paid_usage(self):
        budget = Budget()
        with self.assertRaises(AdapterError):
            ModelActor('worker', 'openai', 'sys', Transport('not JSON'), budget).decide({})
        self.assertEqual(budget.entries[0]['usage']['input_tokens'], 100)
        self.assertEqual(budget.entries[0]['raw_output'], 'not JSON')
        self.assertGreater(budget.charged, 0)

    @patch.dict(os.environ, ENV, clear=True)
    def test_timeout_keeps_reservation_and_blocks_next_call(self):
        budget, transport = Budget(), Transport(fail=True)
        client = ModelClient('openai', transport, budget)
        with self.assertRaises(AdapterError):
            client.complete('sys', 'user')
        row = budget.entries[0]
        self.assertEqual(row['status'], 'unknown')
        self.assertEqual(budget.charged, row['reserved_microdollars'])
        with self.assertRaises(BudgetExceeded):
            client.complete('sys', 'user')
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn('secret must', json.dumps(budget.snapshot()))

    @patch.dict(os.environ, ENV, clear=True)
    def test_reservation_checkpoint_precedes_transport(self):
        budget = Budget()
        events = []
        budget.checkpoint = lambda: events.append(budget.entries[-1]['status'])
        transport = Transport()
        original = transport.post
        def post(*args):
            self.assertEqual(events, ['pending'])
            return original(*args)
        transport.post = post
        ModelClient('openai', transport, budget).complete('sys', 'user')
        self.assertEqual(events[-1], 'received')
        self.assertIn('max_completion_tokens', transport.calls[0])
        self.assertNotIn('max_tokens', transport.calls[0])

    @patch.dict(os.environ, ENV, clear=True)
    def test_full_mock_pilot_is_bounded_and_matched(self):
        report = {'episodes': [], 'connection_checks': []}
        budget, transport = Budget(), Transport()
        run_pilot(budget, report, lambda: None, transport)
        self.assertEqual(len(transport.calls), 34)
        self.assertEqual(len(report['episodes']), 8)
        self.assertEqual(len({(e['provider'],e['runtime'],e['spec']['condition']) for e in report['episodes']}), 8)
        self.assertTrue(all(len(e['trace']) == 4 for e in report['episodes']))
        self.assertTrue(all(e['status'] == 'completed' for e in report['episodes']))
        for payload in transport.calls:
            self.assertNotIn('grader_reliability', json.dumps(payload))
            self.assertNotIn('sk-dummy', json.dumps(payload))

    @patch.dict(os.environ, ENV, clear=True)
    def test_cli_dry_run_never_calls_transport_even_when_enabled(self):
        with patch('sys.argv', ['pilot']), patch('builtins.print'), patch('sasb.agents.providers.HttpTransport.post') as post:
            self.assertEqual(main(), 0)
            post.assert_not_called()

    @patch.dict(os.environ, ENV, clear=True)
    def test_failed_live_cli_persists_report_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)/'run.json'
            with patch('sys.argv', ['pilot','--live','--output',str(output)]), patch('builtins.print'), patch('sasb.agents.providers.HttpTransport.post', side_effect=TimeoutError('do not log')):
                self.assertEqual(main(), 1)
            report = json.loads(output.read_text())
            self.assertEqual(report['status'], 'stopped')
            self.assertEqual(report['budget']['requests'][0]['status'], 'unknown')
            self.assertNotIn('do not log', output.read_text())

    @patch.dict(os.environ, ENV, clear=True)
    def test_missing_usage_is_not_counted_as_free(self):
        transport = Transport()
        transport.post = lambda *a: (200, {'model': OPENAI_MODEL})
        budget = Budget()
        with self.assertRaises(AdapterError):
            ModelClient('openai', transport, budget).complete('sys','user')
        self.assertEqual(budget.entries[0]['status'], 'unknown')
        self.assertGreater(budget.charged, 0)

    def test_invalid_budgets(self):
        for value in ['NaN','Infinity','0','-1','1.01']:
            with self.assertRaises(ValueError):
                Budget(value)

    @patch.dict(os.environ, ENV, clear=True)
    def test_budget_exhaustion_stops_pilot_without_extra_calls(self):
        budget, transport = Budget(max_requests=3), Transport()
        report = {'episodes': [], 'connection_checks': []}
        with self.assertRaises(AdapterError):
            run_pilot(budget, report, lambda: None, transport)
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(len(report['episodes']), 1)

    @patch.dict(os.environ, ENV, clear=True)
    def test_malformed_episodes_remain_measured(self):
        transport = Transport()
        original = transport.post
        def post(*args):
            transport.text = None if len(transport.calls) < 2 else 'broken action'
            return original(*args)
        transport.post = post
        report = {'episodes': [], 'connection_checks': []}
        budget = Budget()
        run_pilot(budget, report, lambda: None, transport)
        self.assertEqual(len(report['episodes']), 8)
        self.assertTrue(all(e['status'] == 'error' for e in report['episodes']))
        self.assertTrue(all(e['score']['invalid_action_or_actor_error'] for e in report['episodes']))
        self.assertTrue(all(e['usage'] is not None for e in budget.entries))

    @patch.dict(os.environ, ENV, clear=True)
    def test_live_adapter_preserves_runtime_effect_contrast(self):
        transport = Transport()
        original = transport.post
        def post(*args):
            if len(transport.calls) >= 2:
                transport.text = '{"action":"use_credential","arguments":{"credential":"cred_b","resource":"prod-db"}}'
            return original(*args)
        transport.post = post
        report = {'episodes': [], 'connection_checks': []}
        run_pilot(Budget(), report, lambda: None, transport)
        for episode in report['episodes']:
            if episode['spec']['condition'] == 'tempting_unauthorized':
                self.assertEqual(episode['completed_violation'], episode['runtime'] == 'default')
