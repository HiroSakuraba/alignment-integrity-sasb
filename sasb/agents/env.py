"""Literal KEY=value loader. Existing environment wins. No shell evaluation."""

import os
from pathlib import Path

from .providers import KEY_ENV, MODEL_ENV, ProviderConfigError


def load_env(path=".env"):
    path = Path(path)
    if not path.exists():
        return
    allowed = set(KEY_ENV.values()) | set(MODEL_ENV.values()) | {
        "SASB_ENABLE_NETWORK",
        "SASB_PROVIDER_VALIDATED",
        "SASB_OPENAI_REASONING_EFFORT",
    }
    values = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or name not in allowed or name in values:
            raise ProviderConfigError("invalid .env entry on line %d" % number)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    for name, value in values.items():
        os.environ.setdefault(name, value)
