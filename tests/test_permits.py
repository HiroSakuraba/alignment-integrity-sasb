import os
import tempfile
import unittest

from sasb.runtime.permits import PermitError, PermitStore


class PermitTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        self.store = PermitStore(self.path, b"k" * 32)

    def tearDown(self):
        self.store.close()
        os.unlink(self.path)

    def test_consume_once(self):
        payload = {"action": "write", "resource": "test-db", "tenant": "tenant_a"}
        token = self.store.issue(payload)
        self.assertEqual(len(self.store.consume(token, payload)), 32)
        with self.assertRaises(PermitError):
            self.store.consume(token, payload)

    def test_binding_mismatch(self):
        token = self.store.issue({"action": "write"})
        with self.assertRaises(PermitError):
            self.store.verify(token, {"action": "read"})


if __name__ == "__main__":
    unittest.main()
