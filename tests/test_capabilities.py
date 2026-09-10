import unittest

from sasb.runtime.capabilities import CapabilityError, CapabilityService


class CapabilityTests(unittest.TestCase):
    def test_delegation_cannot_expand(self):
        service = CapabilityService()
        service.grant("worker-1", "write", "test-db", "tenant_a")
        with self.assertRaises(CapabilityError):
            service.delegate("worker-1", "planner-1", "write", "prod-db", "tenant_b")
        service.delegate("worker-1", "planner-1", "write", "test-db", "tenant_a")
        self.assertTrue(service.authorized("planner-1", "write", "test-db", "tenant_a"))


if __name__ == "__main__":
    unittest.main()
