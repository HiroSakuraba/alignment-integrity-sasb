import unittest
from unittest.mock import patch
from sasb.recovery import run_case, history_probe, JobStream, WORKER
from sasb.reachability import reachable
from sasb.live import violation_reachable, should_pay
from sasb.world import World
from sasb.scenarios.maintenance import specification

class RecoveryTests(unittest.TestCase):
    def test_stop_is_not_recovery(self):
        r = run_case(policy='all_stop')['metrics']
        self.assertFalse(r['recovered'])
        self.assertEqual(r['jobs_completed'],0)
        self.assertEqual(r['phi'],0)
        self.assertEqual(r['scheduled_recovery_opportunities'],24)

    def test_memory_controls_and_authorized_twin(self):
        retained = run_case()['metrics']
        cleared = run_case(intervention='clear')['metrics']
        filler = run_case(intervention='filler')['metrics']
        self.assertFalse(retained['recovered'])
        self.assertEqual(retained['completed_violations'],0)
        self.assertGreater(retained['recovery_proposals'],0)
        self.assertEqual(cleared['recovery_time'],8)
        self.assertGreater(filler['recovery_time'],cleared['recovery_time'])
        self.assertTrue(run_case(burst='authorized')['metrics']['recovered'])
        self.assertTrue(run_case(memory_mode='evidence')['metrics']['recovered'])
        self.assertFalse(run_case(policy='fixed')['metrics']['displaced'])

    def test_cleanup_does_not_erase_historical_harm(self):
        r = run_case(runtime='default',intervention='clear')['metrics']
        self.assertTrue(r['recovered'])
        self.assertGreater(r['completed_violations'],0)

    def test_fresh_jobs_do_not_restore_revoked_permissions(self):
        r = run_case(policy='fixed',revoked=True)['metrics']
        self.assertEqual(r['jobs_offered'],13)
        self.assertEqual(r['jobs_completed'],0)
        self.assertFalse(r['recovered'])

    def test_completion_requires_fresh_write_and_unique_job(self):
        stream = JobStream(World(specification('authorized_maintenance')))
        receipt = dict(action='complete_maintenance',decision='executed')
        writes = [dict(tenant='tenant_a',resource='test-db')]
        stream.offer(0)
        self.assertIsNotNone(stream.credit(receipt,writes,1))
        self.assertIsNone(stream.credit(receipt,writes,2))
        stream.offer(4)
        self.assertIsNone(stream.credit(receipt,[],5))
        self.assertIsNotNone(stream.credit(receipt,writes,6))

    def test_seeded_distribution_and_replay(self):
        runs = [run_case(policy='stochastic',intervention='clear',seed=s) for s in range(64)]
        self.assertGreater(len({r['metrics']['recovery_time'] for r in runs}),1)
        for r in runs:
            self.assertTrue(0 <= r['metrics']['phi'] <= 1)
            self.assertEqual(r['metrics']['completed_violations'],0)
        self.assertEqual(runs[0],run_case(policy='stochastic',intervention='clear',seed=0))
        replay = run_case(policy='stochastic',intervention='clear',replay=runs[0]['trace'])
        self.assertEqual(replay['trace'],runs[0]['trace'])
        self.assertEqual(replay['metrics'],runs[0]['metrics'])

    def test_permission_snapshot_insufficient_for_next_action(self):
        a,b = history_probe('attack'),history_probe('authorized')
        self.assertEqual(a['projection'],b['projection'])
        self.assertNotEqual(a['action'],b['action'])
        self.assertEqual(history_probe('attack','evidence')['action'],history_probe('authorized','evidence')['action'])

    def test_truncated_search_is_unknown_and_does_not_skip(self):
        r = reachable('authorized_maintenance',max_states=1)
        self.assertFalse(r['exhausted'])
        self.assertIsNone(r['violation_reachable'])
        with patch('sasb.live._exhaustive_reachable',return_value=r):
            self.assertIsNone(violation_reachable('authorized_maintenance','proposed','worker'))
        self.assertTrue(should_pay(None,'adversary',False))
        self.assertFalse(should_pay(0,'adversary',False))
        self.assertTrue(should_pay(0,'honest',False))
