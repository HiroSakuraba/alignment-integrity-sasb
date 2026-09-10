"""HMAC permits bound to action, resource, recipient, and capability scope.

Copied in spirit from HiroSakuraba/controlled-ai-research. This is a local
demonstration signer, not a production public-key issuer.
"""

import hashlib
import hmac
import json
import sqlite3
import uuid


class PermitError(ValueError):
    pass


class PermitStore:
    def __init__(self, path, key):
        if len(key) < 32:
            raise ValueError("use at least 32 key bytes")
        self.key = key
        self.db = sqlite3.connect(path)
        self.db.isolation_level = "IMMEDIATE"
        self.db.execute("CREATE TABLE IF NOT EXISTS used (nonce TEXT PRIMARY KEY)")
        self.db.commit()
        self.db.execute("PRAGMA busy_timeout=5000")

    def close(self):
        self.db.close()

    def issue(self, payload, exp=None):
        body = json.dumps(
            {"nonce": uuid.uuid4().hex, "payload": payload, "exp": exp},
            sort_keys=True,
            separators=(",", ":"),
        )
        return {"body": body, "mac": hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()}

    def verify(self, token, payload, clock=None):
        try:
            if set(token) != {"body", "mac"}:
                raise PermitError("unexpected token fields")
            expected = hmac.new(self.key, token["body"].encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, token["mac"]):
                raise PermitError("invalid signature")
            body = json.loads(token["body"])
            if set(body) != {"nonce", "payload", "exp"} or body["payload"] != payload:
                raise PermitError("binding mismatch")
            if body["exp"] is not None and clock is not None and clock >= body["exp"]:
                raise PermitError("expired")
            return body
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise PermitError("malformed token") from exc

    def consume(self, token, payload, clock=None):
        body = self.verify(token, payload, clock)
        try:
            with self.db:
                self.db.execute("INSERT INTO used VALUES (?)", (body["nonce"],))
        except sqlite3.IntegrityError as exc:
            raise PermitError("already consumed") from exc
        return body["nonce"]
