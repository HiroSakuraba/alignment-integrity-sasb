"""Single-use spend permits for paid live requests.

A reservation is taken before HTTP. Missing usage keeps the reservation and
blocks later calls so an in-flight request cannot be treated as free. The
numbers are local estimates against pinned model rates, not a provider invoice.

Each reservation is sized from the request that is about to be sent: an upper
bound on its prompt tokens (UTF-8 bytes of system + user text plus a fixed
framing allowance) and the request's max output tokens. Both pinned providers
use byte-level BPE tokenizers, so one token never covers less than one byte;
the byte count can only over-count the billed input. Because max output tokens
also caps billed output, a settled request can never cost more than its
reservation, and a reservation is only granted if it fits under the cap.
"""
from __future__ import annotations

import fcntl
import math
from pathlib import Path

from .costs import RATES


def _cost_up(model, input_tokens, output_tokens):
    """Pinned-rate cost rounded UP to the micro-dollar, so the ledger never
    under-counts (costs.usage_usd rounds to nearest)."""
    rate = RATES[model]
    exact = (int(input_tokens) * rate.input_per_million
             + int(output_tokens) * rate.output_per_million) / 1_000_000
    return math.ceil(round(exact * 1_000_000, 6)) / 1_000_000


def ledger_usd(model, usage):
    if model not in RATES:
        return 0.0
    return _cost_up(model, usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0)


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


# Per-request framing tokens the provider adds around system/user text
# (role markers, message separators). Generous on purpose.
PROMPT_FRAMING_TOKENS = 32

# Refuse to reserve above this prompt bound. Keeps every request well below
# long-context price tiers, so the flat pinned rate stays an upper bound.
MAX_PROMPT_TOKEN_BOUND = 100_000


def prompt_token_bound(*texts):
    """Upper bound on billed input tokens for the given prompt texts.

    Byte-level BPE tokens cover at least one byte each, so UTF-8 byte length
    cannot under-count. Framing tokens are added once per request.
    """
    total = 0
    for text in texts:
        if text is None:
            continue
        if not isinstance(text, str):
            text = str(text)
        total += len(text.encode("utf-8"))
    return total + PROMPT_FRAMING_TOKENS


def reserve_cost(model, input_tokens, output_tokens, margin=1.0):
    """Reservation for one request. Never claims cache savings.

    ``input_tokens`` should already be an upper bound (see prompt_token_bound);
    ``margin`` >= 1 optionally pads it further.
    """
    if model not in RATES:
        raise ValueError("no pinned rate for %r" % model)
    if margin < 1:
        raise ValueError("margin must be >= 1")
    padded = int(math.ceil(int(input_tokens) * float(margin)))
    return _cost_up(model, padded, int(output_tokens))


class RequestBudget:
    """Serial pre-request ledger. One unresolved ticket blocks the next reserve."""

    def __init__(
        self,
        cap_usd,
        model,
        max_requests=64,
        input_tokens=1152,
        output_tokens=256,
        margin=1.0,
    ):
        """``input_tokens``/``output_tokens`` are only the fallback size used for
        the pre-flight check before any request has been seen. Real reservations
        are sized from each request's prompt bound and max output tokens."""
        if isinstance(cap_usd, bool) or cap_usd is None:
            raise ValueError("cap_usd must be a finite non-negative number")
        cap = float(cap_usd)
        if not math.isfinite(cap) or cap < 0:
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
        if self.margin < 1:
            raise ValueError("margin must be >= 1")
        self.last_input_tokens = None
        self.last_output_tokens = None
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

    def _size(self, input_tokens=None, output_tokens=None):
        if input_tokens is None:
            input_tokens = self.last_input_tokens if self.last_input_tokens is not None else self.input_tokens
        if output_tokens is None:
            output_tokens = self.last_output_tokens if self.last_output_tokens is not None else self.output_tokens
        return int(input_tokens), int(output_tokens)

    def request_reserve_usd(self, input_tokens=None, output_tokens=None):
        """Reservation for one request; without arguments, for the most recent
        request size (or the fallback size before the first request)."""
        inp, out = self._size(input_tokens, output_tokens)
        return reserve_cost(self.model, inp, out, self.margin)

    def deny_reason(self, input_tokens=None, output_tokens=None):
        if self.blocked:
            return self.blocked
        if any(row["status"] in {"pending", "unknown"} for row in self.entries):
            return "unresolved request; stop and reconcile provider usage"
        if self.cap_usd <= 0:
            return "dollar_cap"
        inp, out = self._size(input_tokens, output_tokens)
        if inp < 0 or out < 0:
            return "invalid request size"
        if inp > MAX_PROMPT_TOKEN_BOUND:
            return "prompt_too_large"
        if len(self.entries) >= self.max_requests:
            return "request_cap"
        if self.reserved_usd + self.request_reserve_usd(inp, out) > self.cap_usd + 1e-12:
            return "dollar_cap"
        return None

    def can_reserve(self, input_tokens=None, output_tokens=None):
        return self.deny_reason(input_tokens, output_tokens) is None

    def _stop(self, reason):
        self.blocked = reason
        raise BudgetExceeded(reason)

    def reserve(self, input_tokens=None, output_tokens=None):
        """Take a permit for one request of the given size before HTTP.

        ``input_tokens`` must be an upper bound on billed prompt tokens and
        ``output_tokens`` the request's max output tokens.
        """
        inp, out = self._size(input_tokens, output_tokens)
        reason = self.deny_reason(inp, out)
        if reason is not None:
            self._stop(reason)
        amount = self.request_reserve_usd(inp, out)
        self.last_input_tokens, self.last_output_tokens = inp, out
        row = {
            "id": len(self.entries),
            "status": "pending",
            "input_token_bound": inp,
            "max_output_tokens": out,
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
        actual = ledger_usd(self.model, parsed)
        row["usage"] = parsed
        row["status"] = "settled"
        if actual > row["reserved_usd"] + 1e-12:
            # Should be impossible with a byte bound and max output tokens.
            # Account the real cost and stop: the bound assumption broke.
            row["accounted_usd"] = actual
            row["exceeded_reservation"] = True
            self.blocked = "usage exceeded reservation"
            return row
        row["accounted_usd"] = actual
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
            "reservation_rule": "utf8 prompt bytes + %d framing tokens, plus max output tokens, at pinned rates"
            % PROMPT_FRAMING_TOKENS,
            "reserved_usd": self.reserved_usd,
            "settled_usd": self.settled_usd,
            "request_count": self.request_count,
            "blocked": self.blocked,
            "entries": list(self.entries),
        }
