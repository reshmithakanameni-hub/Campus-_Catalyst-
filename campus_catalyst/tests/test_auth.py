import tempfile
import unittest
from pathlib import Path

from campus_catalyst.auth import AuthError, UserStore


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = UserStore(Path(self.dir.name) / "users.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_default_admin_logs_in(self):
        self.assertEqual(self.store.authenticate("admin", "admin123")["role"], "admin")

    def test_password_not_stored_in_plain_text(self):
        self.assertNotIn("admin123", (Path(self.dir.name) / "users.json").read_text())

    def test_register_and_login_case_insensitive_username(self):
        self.store.create_user("Asha_K", "secret1", "Asha Kumar")
        user = self.store.authenticate("asha_k", "secret1")
        self.assertEqual((user["full_name"], user["role"]), ("Asha Kumar", "volunteer"))

    def test_wrong_password_rejected(self):
        with self.assertRaises(AuthError):
            self.store.authenticate("admin", "nope")

    def test_duplicate_and_weak_inputs_rejected(self):
        self.store.create_user("ravi", "secret1", "Ravi")
        for args in (("ravi", "secret1", "Ravi"), ("ab", "secret1", "X"),
                     ("newuser", "123", "X"), ("newuser", "secret1", "")):
            with self.assertRaises(AuthError):
                self.store.create_user(*args)

    def test_change_password_and_persistence(self):
        self.store.change_password("admin", "admin123", "newpass1")
        reloaded = UserStore(Path(self.dir.name) / "users.json")
        self.assertEqual(reloaded.authenticate("admin", "newpass1")["username"], "admin")
        with self.assertRaises(AuthError):
            reloaded.authenticate("admin", "admin123")


if __name__ == "__main__":
    unittest.main()
