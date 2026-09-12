"""Single-use spend permits for paid live requests.

A reservation is taken before HTTP. Missing usage keeps the reservation and
blocks later calls so an in-flight request cannot be treated as free. The
numbers are local estimates against pinned model rates, not a provider invoice.
"""
from __future__ import annotations

import fcntl
from pathlib import Path

from .costs import RATES, usage_usd


class BudgetExceeded(RuntimeError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class FileExistsGuard(RuntimeError):
    pass


class PaidRunLock:
    """Exclusive lock on one host. Does not cover Actions runners or other machines."""

    def __init__(self, path="reports/live-run.lock"):
        self.path = Path(path)
        self._handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "a+")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._handle.close()
            self._handle = None
            raise RuntimeError("another local paid run holds %s" % self.path) from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
        return False


def require_fresh_path(path, force=False):
    dest = Path(path)
    if dest.exists() and not force:
        raise FileExistsGuard("%s already exists; pass --force or choose another --out" % dest)
    return dest


def _usage_dict(usage):
    if usage is None:
        return None
    if hasattr(usage, "input_tokens"):
        return {
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        }
    return {
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
    }


def reserve_cost(model, input_tokens, output_tokens, margin=1.25):
    """Conservative estimate. Inflate input tokens; never claim cache savings."""
    if model not in RATES:
        raise ValueError("no pinned rate for %r" % model)
    padded = int(input_tokens * margin) + int(input_tokens)
    return usage_usd(model, {"input_tokens": padded, "output_tokens": int(output_tokens)})


class RequestBudget:
    """Serial pre-request ledger. One unresolved ticket blocks the next reserve."""

    def __init__(
        self,
        cap_usd,
        model,
        max_requests=64,
        input_tokens=512,
        output_tokens=256,
        margin=1.25,
    ):
        if isinstance(cap_usd, bool) or cap_usd is None:
            raise ValueError("cap_usd must be a finite non-negative number")
        cap = float(cap_usd)
        if cap < 0:
            raise ValueError("cap_usd must be a finite non-negative number")
        if type(max_requests) is not int or max_requests < 0:
            raise ValueError("max_requests must be a non-negative int")
        if model not in RATES:
            raise ValueError("no pinned rate for %r" % model)
        self.cap_usd = cap
        self.model = model
        self.max_requests = max_requests
        self.input_tokens = int(input_tokens)
        self.output_tokens = int(output_tokens)
        self.margin = float(margin)
        self.entries = []
        self.blocked = None

    @property
    def reserved_usd(self):
        return round(sum(row["accounted_usd"] for row in self.entries), 6)

    @property
    def settled_usd(self):
        return round(
            sum(row["accounted_usd"] for row in self.entries if row["status"] == "settled"),
            6,
        )

    @property
    def request_count(self):
        return len(self.entries)

    def request_reserve_usd(self):
        return reserve_cost(self.model, self.input_tokens, self.output_tokens, self.margin)

    def can_reserve(self):
        if self.blocked:
            return False
        if any(row["status"] in {"pending", "unknown"} for row in self.entries):
            return False
        if self.cap_usd <= 0:
            return False
        if len(self.entries) >= self.max_requests:
            return False
        return self.reserved_usd + self.request_reserve_usd() <= self.cap_usd + 1e-12

    def deny_reason(self):
        if self.blocked:
            return self.blocked
        if any(row["status"] in {"pending", "unknown"} for row in self.entries):
            return "unresolved request; stop and reconcile provider usage"
        if self.cap_usd <= 0 or self.reserved_usd + self.request_reserve_usd() > self.cap_usd + 1e-12:
            return "dollar_cap"
        if len(self.entries) >= self.max_requests:
            return "request_cap"
        return None

    def _stop(self, reason):
        self.blocked = reason
        raise BudgetExceeded(reason)

    def reserve(self):
        if not self.can_reserve():
            self._stop(self.deny_reason())
        amount = self.request_reserve_usd()
        row = {
            "id": len(self.entries),
            "status": "pending",
            "reserved_usd": amount,
            "accounted_usd": amount,
            "usage": None,
        }
        self.entries.append(row)
        return row

    def settle(self, row, usage):
        parsed = _usage_dict(usage)
        if parsed is None or (parsed["input_tokens"] == 0 and parsed["output_tokens"] == 0):
            row["status"] = "unknown"
            self.blocked = "missing usage; reservation retained"
            return row
        actual = usage_usd(self.model, parsed)
        row["usage"] = parsed
        row["accounted_usd"] = actual
        row["status"] = "settled"
        if self.reserved_usd > self.cap_usd + 1e-12:
            self.blocked = "dollar_cap"
        return row

    def fail(self, row, reason):
        row["status"] = "unknown"
        self.blocked = reason
        return row

    def snapshot(self):
        return {
            "cap_usd": self.cap_usd,
            "model": self.model,
            "max_requests": self.max_requests,
            "request_reserve_usd": self.request_reserve_usd(),
            "reserved_usd": self.reserved_usd,
            "settled_usd": self.settled_usd,
            "request_count": self.request_count,
            "blocked": self.blocked,
            "entries": list(self.entries),
        }
