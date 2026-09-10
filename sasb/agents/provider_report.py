"""Local provider readiness report. No network calls and no key values."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .providers import (
    ANTHROPIC_MODEL,
    KEY_ENV,
    MODEL_ENV,
    OPENAI_MODEL,
    describe_setup,
    live_calls_allowed,
)


ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
}


def _flag(name):
    raw = os.environ.get(name)
    return {"name": name, "set": raw is not None, "is_one": raw == "1"}


def _key_shape(provider):
    raw = os.environ.get(KEY_ENV[provider], "")
    present = bool(raw.strip())
    if not present:
        return {"present": False, "prefix_ok": None}
    if provider == "openai":
        return {"present": True, "prefix_ok": raw.startswith("sk-")}
    return {"present": True, "prefix_ok": raw.startswith("sk-ant-")}


def _reasoning_status():
    raw = os.environ.get("SASB_OPENAI_REASONING_EFFORT", "none")
    requested = (raw or "none").strip() or "none"
    return {"requested": requested, "allowed": requested == "none", "required": "none"}


def setup_report(env_path=".env"):
    env_path = Path(env_path)
    base = describe_setup()
    rows = []
    for row in base["providers"]:
        shape = _key_shape(row["provider"])
        extra = dict(row)
        extra["key_env"] = KEY_ENV[row["provider"]]
        extra["key_prefix_ok"] = shape["prefix_ok"]
        extra["endpoint"] = ENDPOINTS[row["provider"]]
        extra["model_env"] = MODEL_ENV[row["provider"]]
        rows.append(extra)
    reasoning = _reasoning_status()
    pins_ok = all(row["model_allowed"] for row in rows)
    keys_present = all(row["key_present"] for row in rows)
    prefixes_ok = all(row["key_prefix_ok"] is not False for row in rows)
    live = live_calls_allowed()
    if not pins_ok:
        status = "blocked_bad_pin"
    elif not reasoning["allowed"]:
        status = "blocked_reasoning_upgrade"
    elif live and keys_present and prefixes_ok:
        status = "live_armed"
    elif keys_present and prefixes_ok:
        status = "ready_for_live_after_flags"
    elif keys_present:
        status = "blocked_key_prefix"
    else:
        status = "offline_missing_keys"
    next_steps = []
    if not env_path.exists():
        next_steps.append("copy .env.example to .env and add keys locally")
    if not keys_present:
        next_steps.append("set OPENAI_API_KEY and ANTHROPIC_API_KEY in .env")
    if not pins_ok:
        next_steps.append("reset model ids to gpt-5.6-luna and claude-haiku-4-5-20251001")
    if not reasoning["allowed"]:
        next_steps.append("set SASB_OPENAI_REASONING_EFFORT=none")
    if status == "ready_for_live_after_flags":
        next_steps.append("leave SASB_ENABLE_NETWORK and SASB_PROVIDER_VALIDATED unset until a paid run is intended")
    if status == "live_armed":
        next_steps.append("network flags are on; this report still made no HTTP request")
    if not next_steps:
        next_steps.append("dry-run complete; keep network flags unset")
    return {
        "claim": "Local provider setup report. No network call. No key values. No paid run.",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "network_called": False,
        "status": status,
        "live_calls_allowed": live,
        "pins_ok": pins_ok,
        "keys_present": keys_present,
        "env_file": {
            "path": str(env_path),
            "exists": env_path.exists(),
            "loader": "literal KEY=value if a loader is present; existing environment wins",
        },
        "flags": [
            _flag("SASB_ENABLE_NETWORK"),
            _flag("SASB_PROVIDER_VALIDATED"),
        ],
        "reasoning": reasoning,
        "request_contract": {
            "openai_chat_completions": {
                "model": OPENAI_MODEL,
                "endpoint": ENDPOINTS["openai"],
                "max_tokens": 256,
                "reasoning_effort": "none",
            },
            "anthropic_messages": {
                "model": ANTHROPIC_MODEL,
                "endpoint": ENDPOINTS["anthropic"],
                "max_tokens": 256,
                "extended_thinking": False,
            },
            "served_model_policy": "accept Luna or Haiku 4.5 ids; reject Sol, Terra, Sonnet, Opus",
        },
        "providers": rows,
        "next_steps": next_steps,
    }


def write_setup_report(path="reports/provider-setup-local.json", env_path=".env"):
    report = setup_report(env_path)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    report["written_to"] = str(dest)
    return report
