"""Per-cell rates with 95% Wilson intervals for repeated live episodes."""

import math
from math import comb

Z95 = 1.959963984540054

# Episode-level outcomes reported per cell. Each is a score field that is True,
# False, or None (None = not applicable to that condition, left out of n).
CELL_METRICS = (
    "completed_violation",
    "prohibited_attempt",
    "malformed_write_target",
    "authorized_task_completion",
    "false_refusal",
    "appropriate_uncertainty_handling",
    "valid_correction_acceptance",
    "ack_loop",
    "revocation_cited_stop",
    "first_turn_stop",
    "model_stop",
    "invalid_action_or_actor_error",
    "format_retry_used",
)


def wilson(successes, total, z=Z95):
    """Two-sided Wilson score interval. None when there are no trials."""
    if total <= 0:
        return None
    if not 0 <= successes <= total:
        raise ValueError("successes must be between 0 and total")
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def rate(values):
    """k, n, rate and interval for a list of True/False/None outcomes."""
    applicable = [bool(v) for v in values if v is not None]
    n = len(applicable)
    k = sum(applicable)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "wilson95": wilson(k, n)}


def fisher_two_sided(a, b, c, d):
    """Two-sided Fisher exact test for the 2x2 table [[a, b], [c, d]].

    Sums the probabilities of every table with the same margins that is no
    more likely than the observed one.
    """
    n, row1, col1 = a + b + c + d, a + b, a + c
    if n == 0:
        return 1.0

    def prob(x):
        return comb(row1, x) * comb(n - row1, col1 - x) / comb(n, col1)

    observed = prob(a)
    lo, hi = max(0, col1 - (n - row1)), min(row1, col1)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= observed * (1 + 1e-9)))


def newcombe_diff(k1, n1, k2, n2, confidence=0.90):
    """Newcombe hybrid score interval for p1 - p2 (method 10, 1998).

    Built from the two Wilson intervals at the same confidence. A 90% interval
    lying inside (-d, d) is the two one-sided tests equivalence check at 0.05.
    """
    if n1 <= 0 or n2 <= 0:
        return None
    z = {0.90: 1.6448536269514722, 0.95: Z95}[confidence]
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = _wilson_raw(k1, n1, z)
    l2, u2 = _wilson_raw(k2, n2, z)
    diff = p1 - p2
    return (round(diff - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), 4),
            round(diff + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2), 4))


def _wilson_raw(successes, total, z):
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


# Rows from runs before history prefixes existed have no prefix: they are h0.
_KEY_DEFAULTS = {"history_prefix": "h0"}


def cell_table(rows, keys=("role", "runtime", "feedback", "revocation_observation_mode", "history_prefix",
                           "condition"), metrics=CELL_METRICS):
    """Group scored rows by ``keys`` and report every metric with its interval."""
    groups = {}
    for row in rows:
        if row.get("completed_violation") is None:
            continue
        label = "|".join(str(row.get(k, _KEY_DEFAULTS.get(k))) for k in keys)
        groups.setdefault(label, []).append(row)
    table = {}
    for label, members in sorted(groups.items()):
        entry = {k: members[0].get(k, _KEY_DEFAULTS.get(k)) for k in keys}
        entry["episodes"] = len(members)
        entry["metrics"] = {m: rate([r.get(m) for r in members]) for m in metrics}
        table[label] = entry
    return table
