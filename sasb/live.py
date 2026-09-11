"""Zero-cost-first Stage B driver. Scripted dry-run; pinned Luna/Haiku when armed.

The maintenance matrix stays scripted. This module attaches ModelActor to the
existing harness without changing frozen Stage A reports. Live calls still
require SASB_ENABLE_NETWORK=1 and SASB_PROVIDER_VALIDATED=1.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .agents.providers import (
    ANTHROPIC_MODEL,
    OPENAI_MODEL,
    ModelActor,
    ProviderDisabled,
    live_calls_allowed,
    load_env,
    require_live,
)
from .agents.roles import DEFAULT_ROSTER
from .costs import usage_usd
from .harness import run_episode
from .policies import actors_for
from .runtime.treatments import DEFAULT, PROPOSED
from .scenarios.maintenance import CONDITIONS
from .scoring.scorecard import summarize


ROLE_PROMPTS = {
    "coordinator": "coordinator-v1.txt",
    "planner": "planner-v1.txt",
    "worker": "worker-v1.txt",
    "reviewer": "reviewer-v1.txt",
}


def load_prompt(name):
    return (Path(__file__).resolve().parents[1] / "prompts" / name).read_text()


def model_for(provider):
    if provider == "anthropic":
        return ANTHROPIC_MODEL
    if provider == "openai":
        return OPENAI_MODEL
    return None


def actors_for_live(condition, provider, transport=None, model_roles=("worker-1",)):
    """Scripted peers; pinned ModelActor on selected roles."""
    actors = actors_for(condition, "compliant")
    roster = {row["agent_id"]: row["role"] for row in DEFAULT_ROSTER}
    for agent_id in model_roles:
        role = roster[agent_id]
        prompt = load_prompt(ROLE_PROMPTS[role])
        actors[agent_id] = ModelActor(role, provider, prompt, transport=transport)
    return actors


def _compact(episode):
    score = episode["score"]
    return {
        "condition": episode["spec"]["condition"],
        "policy": episode["policy"],
        "runtime": episode["runtime"],
        "mode": episode["mode"],
        "completed_violation": score["completed_violation"],
        "unauthorized_attempt": score["unauthorized_attempt"],
        "authorized_task_completion": score["authorized_task_completion"],
        "invalid_action_or_actor_error": score["invalid_action_or_actor_error"],
        "usage": episode.get("usage") or {},
        "provider": episode["record"].get("provider"),
        "model": episode["record"].get("model"),
        "network": episode["record"].get("network"),
        "observation_has_available_actions": "available_actions" in episode.get("agent_observation_keys", []),
    }


def run_experiment(
    provider="local",
    dry_run=True,
    conditions=CONDITIONS,
    runtime=PROPOSED,
    mode="worker",
    cap_usd=1.0,
    transport=None,
    model_roles=("worker-1",),
):
    if runtime not in {DEFAULT, PROPOSED}:
        raise ValueError("unknown runtime")
    if not dry_run:
        load_env()
        require_live()
        if provider not in {"anthropic", "openai"}:
            raise ValueError("live provider must be anthropic or openai")
        if not live_calls_allowed():
            raise ProviderDisabled("live flags are off")
    model = None if dry_run else model_for(provider)
    usage = {"input_tokens": 0, "output_tokens": 0, "retries": 0}
    spent = 0.0
    rows = []
    scores = []
    if dry_run:
        policies = ("compliant", "noncompliant")
    else:
        policies = ("model",)
    planned = [(condition, policy) for condition in conditions for policy in policies]
    for condition, policy in planned:
        if dry_run:
            episode = run_episode(condition, policy, runtime=runtime, mode=mode)
        else:
            actors = actors_for_live(condition, provider, transport=transport, model_roles=model_roles)
            episode = run_episode(
                condition,
                policy,
                runtime=runtime,
                mode=mode,
                actors=actors,
                provider=provider,
            )
        cell_usage = episode.get("usage") or {}
        for key in usage:
            usage[key] += int(cell_usage.get(key, 0) or 0)
        paid = not dry_run
        if paid and model:
            spent = round(spent + usage_usd(model, cell_usage), 6)
        rows.append({**_compact(episode), "paid": paid})
        scores.append(episode["score"])
        if paid and spent >= cap_usd:
            break
    return {
        "claim": (
            "Stage B rehearsal. ScriptedActor only."
            if dry_run
            else "Pinned Luna/Haiku worker on the maintenance conditions."
        ),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": dry_run,
        "network_called": bool(not dry_run),
        "provider": "local" if dry_run else provider,
        "model": model,
        "runtime": runtime,
        "mode": mode,
        "model_roles": list(model_roles),
        "conditions": list(conditions),
        "summary": summarize(scores) if scores else {},
        "rows": rows,
        "usage": usage,
        "spent_usd": spent,
        "cap_usd": cap_usd,
        "priced_from": "reported usage tokens against pinned model rates",
        "stopped": "dollar_cap" if not dry_run and spent >= cap_usd else "episode_cap",
        "notes": [
            "Frozen Stage A reports are unchanged. This driver is a separate report.",
            "Worker-only mode is the cheap cell. Swarm mode still uses scripted peers unless listed in model_roles.",
            "Parse failures are adapter_error outcomes and are not retried.",
            "Evaluator-only fields stay out of observations.",
        ],
    }


def write_report(report, path="reports/live-run-local.json"):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    out = dict(report)
    out["written_to"] = str(dest)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="SASB Stage B experiment driver")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--provider", choices=("local", "anthropic", "openai"), default="local")
    parser.add_argument("--runtime", choices=(PROPOSED, DEFAULT), default=PROPOSED)
    parser.add_argument("--mode", choices=("worker", "swarm"), default="worker")
    parser.add_argument("--cap-usd", type=float, default=1.0)
    parser.add_argument("--out", default="reports/live-run-local.json")
    args = parser.parse_args(argv)
    dry_run = args.dry_run or args.provider == "local"
    report = run_experiment(
        provider=args.provider,
        dry_run=dry_run,
        runtime=args.runtime,
        mode=args.mode,
        cap_usd=args.cap_usd,
    )
    report = write_report(report, args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    main()
