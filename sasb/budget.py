"""Pre-request spending ledger for paid live cells.

This is a local estimate against pinned model rates. It is not a provider
billing cap. Reserve before a request; missing usage keeps the reservation
and blocks later calls so an in-flight request cannot be treated as free.
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
    """Exclusive local lock. Does not cover GitHub Actions or other hosts."""

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
        raise FileExistsGuard(
            "%s already exists; pass force=True or choose another --out" % dest
        )
    return dest


def reserve_cost(model, input_tokens, output_tokens, margin=1.25):
    """Conservative estimate: inflate input tokens, never claim cache savings."""
    if model not in RATES:
        raise ValueError("no pinned rate for %r" % model)
    padded = int(input_tokens * margin) + input_tokens
    return usage_usd(model, {"input_tokens": padded, "output_tokens": int(output_tokens)})


class RequestBudget:
    def __init__(
        self,
        cap_usd,
        model,
        max_requests=64,
        input_tokens=512,
        output_tokens=256,
        margin=1.25,
        calls_per_cell=4,
        checkpoint=None,
    ):
        if type(cap_usd) is bool or cap_usd is None:
            raise ValueError("cap_usd must be a finite non-negative number")
        cap = float(cap_usd)
        if cap < 0:
            raise ValueError("cap_usd must be a finite non-negative number")
        if type(max_requests) is not int or max_requests < 0:
            raise ValueError("max_requests must be a non-negative int")
        self.cap_usd = cap
        self.model = model
        self.max_requests = max_requests
        self.input_tokens = int(input_tokens)
        self.output_tokens = int(output_tokens)
        self.margin = float(margin)
        self.calls_per_cell = int(calls_per_cell)
        self.checkpoint = checkpoint or (lambda: None)
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

    def cell_reserve_usd(self):
        return round(self.calls_per_cell * reserve_cost(
            self.model, self.input_tokens, self.output_tokens, self.margin
        ), 6)

    def _stop(self, reason):
        self.blocked = reason
        self.checkpoint()
        raise BudgetExceeded(reason)

    def reserve(self, kind="cell"):
        if self.blocked:
            raise BudgetExceeded(self.blocked)
        if any(row["status"] in {"pending", "unknown"} for row in self.entries):
            self._stop("unresolved request; stop and reconcile provider usage")
        if self.cap_usd <= 0:
            self._stop("dollar_cap")
        if len(self.entries) >= self.max_requests:
            self._stop("request_cap")
        amount = self.cell_reserve_usd() if kind == "cell" else reserve_cost(
            self.model, self.input_tokens, self.output_tokens, self.margin
        )
        if self.reserved_usd + amount > self.cap_usd + 1e-12:
            self._stop("dollar_cap")
        row = {
            "kind": kind,
            "status": "pending",
            "reserved_usd": amount,
            "accounted_usd": amount,
            "usage": None,
        }
        self.entries.append(row)
        self.checkpoint()
        return row

    def settle(self, row, usage):
        if usage is None or (
            int(usage.get("input_tokens", 0) or 0) == 0
            and int(usage.get("output_tokens", 0) or 0) == 0
        ):
            row["status"] = "unknown"
            self.blocked = "missing usage; reservation retained"
            self.checkpoint()
            return row
        actual = usage_usd(self.model, usage)
        row["usage"] = {
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
        }
        row["accounted_usd"] = actual
        row["status"] = "settled"
        self.checkpoint()
        return row

    def fail(self, row, reason):
        row["status"] = "unknown"
        self.blocked = reason
        self.checkpoint()
        return row
