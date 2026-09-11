"""Deterministic token pricing for pinned Luna/Haiku ids."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rate:
    input_per_million: float
    output_per_million: float


RATES = {
    "gpt-5.6-luna": Rate(0.20, 1.20),
    "claude-haiku-4-5-20251001": Rate(1.0, 5.0),
    "claude-haiku-4-5": Rate(1.0, 5.0),
    "claude-haiku-4.5": Rate(1.0, 5.0),
}


def estimate(model, input_tokens, output_tokens):
    rate = RATES[model] if isinstance(model, str) else model
    return round(
        (input_tokens * rate.input_per_million + output_tokens * rate.output_per_million) / 1_000_000,
        6,
    )


def usage_usd(model, usage):
    if model not in RATES:
        return 0.0
    return estimate(
        model,
        int(usage.get("input_tokens", 0) or 0),
        int(usage.get("output_tokens", 0) or 0),
    )
