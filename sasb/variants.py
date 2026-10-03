"""Prompt variants for docs/landscape-robustness-design.md.

A variant is a deterministic rewrite of the text a model receives that should
not change the authority problem. The environment, executor, scoring and
receipts never see a variant: text is rewritten on the way to the model and
the reply is mapped back to canonical identifiers before it is parsed. V0 is
the unchanged text.

- v1, v2: identifiers renamed (same character length; different length and style)
- v3: update-ID format
- v4: user message keys in reverse alphabetical order at every level
- v5: user message indented with two spaces
"""

import hashlib
import json
import re

VARIANTS = ("v0", "v1", "v2", "v3", "v4", "v5")

# Registered in docs/landscape-robustness-design.md; do not change after a run.
IDENTIFIER_MAPS = {
    "v1": {"Alex Rivera": "Dana Moreno", "tenant_a": "tenant_k", "test-db": "main-db", "prod-db": "live-db",
           "cred_a": "cred_m", "cred_b": "cred_n", "worker-1": "worker-7", "update-1": "update-4"},
    "v2": {"Alex Rivera": "Priya Natarajan-Okoye", "tenant_a": "acme-west", "test-db": "staging_inventory",
           "prod-db": "orders_primary", "cred_a": "svc-token-alpha", "cred_b": "svc-token-bravo",
           "worker-1": "agent-0042"},
    "v3": {"update-1": "rev_7f3a9c"},
}

VARIANT_CLASS = {"v0": "none", "v1": "lexical", "v2": "lexical", "v3": "lexical",
                 "v4": "structural", "v5": "structural"}

# An identifier matches only as a whole token: not preceded or followed by a
# character that could continue it.
_TOKEN = "A-Za-z0-9_-"


def _compile(names):
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(r"(?<![%s])(?:%s)(?![%s])" % (_TOKEN, alternatives, _TOKEN))


_FORWARD = {v: (_compile(m), m) for v, m in IDENTIFIER_MAPS.items()}
_INVERSE = {v: (_compile(m.values()), {new: old for old, new in m.items()}) for v, m in IDENTIFIER_MAPS.items()}


def check_variant(variant):
    if variant not in VARIANTS:
        raise ValueError("unknown prompt variant %r; choose from %s" % (variant, ", ".join(VARIANTS)))
    return variant


def _substitute(text, table):
    if table is None or not isinstance(text, str):
        return text
    pattern, mapping = table
    return pattern.sub(lambda m: mapping[m.group(0)], text)


def rewrite(text, variant):
    """Canonical identifiers -> the variant's identifiers (v1-v3 only)."""
    return _substitute(text, _FORWARD.get(check_variant(variant)))


def restore(text, variant):
    """The variant's identifiers -> canonical identifiers (v1-v3 only)."""
    return _substitute(text, _INVERSE.get(check_variant(variant)))


def _reverse_keys(value):
    if isinstance(value, dict):
        return {k: _reverse_keys(value[k]) for k in sorted(value, reverse=True)}
    if isinstance(value, list):
        return [_reverse_keys(v) for v in value]
    return value


def render_user(body, variant="v0"):
    check_variant(variant)
    if variant == "v4":
        return json.dumps(_reverse_keys(body))
    if variant == "v5":
        return json.dumps(body, sort_keys=True, indent=2)
    return json.dumps(body, sort_keys=True)


def render(system, body, variant="v0"):
    """(system text, user text) as the model receives them under ``variant``.

    v0 is byte-identical to what the driver sent before variants existed.
    """
    user = render_user(body, variant)
    return rewrite(system, variant), rewrite(user, variant)


def situation_fingerprint(world, agent_id, observation):
    """Digest of the modeled situation at a model turn, taken before any text
    is rendered: the canonical observation plus the authority, revocation,
    acknowledgment, stop, write and receipt state of the world. Every variant
    of a cell must give the same value."""
    runtime = world.spaces.runtime_view()
    state = {
        "observation": observation,
        "permissions": runtime.get("permissions", {}),
        "revocations": runtime.get("revocations", {}),
        "permission_service_updates": runtime.get("permission_service_updates", {}),
        "acknowledged_updates": {k: sorted(v) for k, v in world.acknowledged_updates.items()},
        "stopped": sorted(world.stopped_agents),
        "writes": list(world.resources.writes),
        "receipts": [(r["agent_id"], r["action"], r["decision"]) for r in world.receipts.dump()],
        "agent_id": agent_id,
    }
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()[:16]
