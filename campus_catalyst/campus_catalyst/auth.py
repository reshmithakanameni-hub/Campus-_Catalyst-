"""Simple user accounts for the web app (standard library only).

Passwords are never stored in plain text: PBKDF2-HMAC-SHA256 with a random salt.
Roles: "admin" (approves hours, manages everything) and "volunteer" (own records only).
"""
import hashlib
import hmac
import json
import os
from pathlib import Path

ROLES = ("admin", "volunteer")
ITERATIONS = 120_000
DEFAULT_ADMIN = ("admin", "admin123")   # demo account; change the password after first login


class AuthError(Exception):
    pass


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return salt.hex(), digest.hex()


def verify_password(password, salt_hex, digest_hex):
    _, candidate = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, digest_hex)


class UserStore:
    def __init__(self, path="data/users.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.users = self._load()
        if not self.users:
            self.create_user(DEFAULT_ADMIN[0], DEFAULT_ADMIN[1], "Administrator", "admin")

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.users, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def create_user(self, username, password, full_name, role="volunteer"):
        username = " ".join(str(username or "").split()).lower()
        full_name = " ".join(str(full_name or "").split())
        if not (3 <= len(username) <= 30) or not username.replace("_", "").replace(".", "").isalnum():
            raise AuthError("Username must be 3-30 letters, digits, '.' or '_'.")
        if not full_name or len(full_name) > 80:
            raise AuthError("Full name is required (80 characters max).")
        if len(str(password or "")) < 6:
            raise AuthError("Password must be at least 6 characters.")
        if role not in ROLES:
            raise AuthError("Unknown role.")
        if username in self.users:
            raise AuthError("That username is already taken.")
        salt, digest = hash_password(password)
        self.users[username] = {"full_name": full_name, "role": role, "salt": salt, "hash": digest}
        self._save()
        return username

    def authenticate(self, username, password):
        """Return {'username', 'full_name', 'role'} or raise AuthError."""
        user = self.users.get(str(username or "").strip().lower())
        if not user or not verify_password(str(password or ""), user["salt"], user["hash"]):
            raise AuthError("Wrong username or password.")
        return {"username": str(username).strip().lower(), "full_name": user["full_name"], "role": user["role"]}

    def change_password(self, username, old_password, new_password):
        self.authenticate(username, old_password)
        if len(new_password) < 6:
            raise AuthError("Password must be at least 6 characters.")
        salt, digest = hash_password(new_password)
        self.users[username]["salt"], self.users[username]["hash"] = salt, digest
        self._save()
