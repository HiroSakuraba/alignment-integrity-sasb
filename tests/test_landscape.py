import unittest
from sasb.landscape import build_landscape


class LandscapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_landscape()

    def test_inventory_complete_and_not_attractor_claim(self):
        rows = self.report['inventory']
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({(r['condition'],r['runtime'],r['policy']) for r in rows}),20)
        self.assertFalse(any(r['attractor_established'] for r in rows))

    def test_coupling_changes_proposal_not_authority(self):
        rows = self.report['coupling']
        for runtime in ('default', 'proposed'):
            group = [r for r in rows if r['runtime']==runtime and r['policy']=='message_rule']
            self.assertEqual(len(group), 3)
            self.assertTrue(all(r['initial_capabilities']==group[0]['initial_capabilities'] for r in group))
            for row in group:
                self.assertEqual(row['out_of_scope_write_proposed'],row['exposure']=='unauthorized')
                self.assertEqual(row['completed_violation'],runtime=='default' and row['exposure']=='unauthorized')

    def test_fixed_script_is_message_insensitive_control(self):
        rows = [r for r in self.report['coupling'] if r['policy']=='fixed_script']
        self.assertTrue(all(r['authorized_task_completion'] for r in rows))
        self.assertFalse(any(r['out_of_scope_write_proposed'] for r in rows))

    def test_history_projection_and_cleanup_negative_control(self):
        for pair in self.report['history_probes']:
            self.assertTrue(pair['same_projected_snapshot'])
            self.assertEqual(pair['same_full_memory'], pair['cleanup'])
            self.assertEqual(pair['different_proposal_response'], pair['memory_mode']=='unsafe_promote_fixture' and not pair['cleanup'])
            self.assertFalse(any(r['completed_violation'] for r in pair['cases']))
