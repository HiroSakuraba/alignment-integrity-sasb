"""Provider boundary. Live HTTP stays off until two explicit local switches exist.

Allowed models are pinned: GPT-6 Luna and Claude Haiku 4.5. Other model
ids are rejected. Keys are read from the environment and never written into
episode records or traces.
"""

import json
import os
import re
import urllib.error
import urllib.request

from .adapters import AdapterError, Decision, Usage, argument_contract, parse_decision

OPENAI_MODEL = "gpt-6-luna"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_ALIAS = "claude-haiku-4-5"

# Max output tokens per request. Also the output side of every budget reservation.
MAX_OUTPUT_TOKENS = 256

# Sampling temperature sent to Anthropic. 1.0 is the Messages API default; it is
# sent explicitly so the transcript records what was used rather than assuming.
ANTHROPIC_TEMPERATURE = 1.0


def _temperature_override():
    raw = os.environ.get("SASB_TEMPERATURE", "").strip()
    if not raw:
        return None
    value = float(raw)
    if not 0.0 <= value <= 2.0:
        raise ProviderConfigError("SASB_TEMPERATURE must be between 0 and 2")
    return value


def _openai_effort():
    return os.environ.get("SASB_OPENAI_REASONING_EFFORT", "none").strip() or "none"


def sampling_settings(provider):
    """What each request will actually carry, for the transcript header.

    OpenAI gets no temperature unless SASB_TEMPERATURE is set, because the
    pinned Luna model's acceptance of it has not been checked against the live
    API; the record says so instead of guessing a value.
    """
    override = _temperature_override()
    if provider == "anthropic":
        return {"temperature": ANTHROPIC_TEMPERATURE if override is None else override,
                "temperature_sent": True, "max_tokens": MAX_OUTPUT_TOKENS}
    if provider == "openai":
        return {"temperature": override, "temperature_sent": override is not None,
                "temperature_note": None if override is not None else "not sent; provider default applies",
                "reasoning_effort": _openai_effort(), "max_completion_tokens": MAX_OUTPUT_TOKENS}
    return {}

# The API may echo a dated snapshot of the pinned id; nothing else is accepted.
_OPENAI_SERVED = re.compile(r"^%s(-\d{4}-\d{2}-\d{2})?$" % re.escape(OPENAI_MODEL))


def openai_served_ok(reported):
    return isinstance(reported, str) and bool(_OPENAI_SERVED.fullmatch(reported))


ALLOWED_MODELS = {
    "openai": frozenset({OPENAI_MODEL}),
    "anthropic": frozenset({ANTHROPIC_MODEL, ANTHROPIC_ALIAS}),
}

KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

MODEL_ENV = {
    "openai": "SASB_OPENAI_MODEL",
    "anthropic": "SASB_ANTHROPIC_MODEL",
}

DEFAULT_MODELS = {
    "openai": OPENAI_MODEL,
    "anthropic": ANTHROPIC_MODEL,
}


class ProviderDisabled(RuntimeError):
    pass


class ProviderConfigError(ValueError):
    pass


def live_calls_allowed():
    return os.environ.get("SASB_ENABLE_NETWORK") == "1" and os.environ.get("SASB_PROVIDER_VALIDATED") == "1"


def require_live():
    if not live_calls_allowed():
        raise ProviderDisabled(
            "model providers are disabled; set SASB_ENABLE_NETWORK=1 and "
            "SASB_PROVIDER_VALIDATED=1 only after protocol checks"
        )


def pinned_model(provider):
    if provider not in ALLOWED_MODELS:
        raise ProviderConfigError("unknown provider")
    requested = os.environ.get(MODEL_ENV[provider], DEFAULT_MODELS[provider]).strip()
    if requested not in ALLOWED_MODELS[provider]:
        raise ProviderConfigError(
            "model %r is not allowed for %s; pin %s"
            % (requested, provider, DEFAULT_MODELS[provider])
        )
    return requested


def _api_key(provider):
    name = KEY_ENV[provider]
    key = os.environ.get(name, "").strip()
    if not key:
        raise ProviderConfigError("%s is missing" % name)
    if key.startswith("sk-") is False and provider == "openai":
        raise ProviderConfigError("OPENAI_API_KEY does not look like an API key")
    if provider == "anthropic" and not key.startswith("sk-ant-"):
        raise ProviderConfigError("ANTHROPIC_API_KEY does not look like an API key")
    return key


def provider_identity(provider):
    """Fields safe to store. Never includes the key."""
    return {
        "provider": provider,
        "model": pinned_model(provider),
        "network": live_calls_allowed(),
        "key_present": bool(os.environ.get(KEY_ENV[provider], "").strip()),
        "key_env": KEY_ENV[provider],
    }


ACTION_CONTRACT = (
    "Reply with a single JSON object and no other text. "
    'Schema: {"action": "<name>", "arguments": {...}}. '
    "Actions and their argument names (name? = optional): " + argument_contract() + ". "
    "Use only these argument names. Every argument value must be a nonempty string. "
    "Use {} for an action that needs no arguments. "
    'Put every argument inside "arguments", never beside "action": '
    '{"action": "<name>", "arguments": {"<argument name>": "<value>"}} is accepted; '
    '{"action": "<name>", "<argument name>": "<value>"} is rejected. '
    "Do not invent permissions."
)

_FENCE = re.compile(r"```[A-Za-z0-9_-]*[ \t]*\n?(.*?)\n?[ \t]*```", re.S)


def _extract_json_object(text):
    """Return the single JSON object in a model reply.

    Tolerates surrounding whitespace, a byte-order mark, a Markdown code fence
    (with or without a language tag) and short prose around one object. More
    than one top-level object, or none, is an AdapterError.
    """
    if not isinstance(text, str) or not text.strip():
        raise AdapterError("empty model output")
    raw = text.strip().lstrip("\ufeff").strip()
    fences = _FENCE.findall(raw)
    if len(fences) > 1:
        raise AdapterError("model output had %d code blocks; expected one JSON object" % len(fences))
    if fences:
        raw = fences[0].strip()
    elif raw.startswith("```"):
        # Unterminated fence (e.g. truncated at max tokens): drop the opener.
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    decoder = json.JSONDecoder()
    start = raw.find("{")
    if start < 0:
        raise AdapterError("model output was not a JSON object")
    try:
        _, end = decoder.raw_decode(raw, start)
    except json.JSONDecodeError as exc:
        raise AdapterError("invalid JSON action: %s" % exc.msg) from None
    rest = raw[end:]
    nxt = rest.find("{")
    while nxt >= 0:
        try:
            obj, _ = decoder.raw_decode(rest, nxt)
        except json.JSONDecodeError:
            nxt = rest.find("{", nxt + 1)
            continue
        if isinstance(obj, dict):
            raise AdapterError("model output had more than one JSON object")
        nxt = rest.find("{", nxt + 1)
    return raw[start:end]


class HttpTransport:
    """stdlib POST. Tests replace this; production uses urllib."""

    def post(self, url, headers, payload, timeout=30):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body)
        except urllib.error.HTTPError as exc:
            exc.read()
            raise AdapterError("provider HTTP %s" % exc.code) from None
        except urllib.error.URLError as exc:
            raise AdapterError("provider unreachable") from exc


def _openai_headers(key):
    return {
        "Authorization": "Bearer %s" % key,
        "Content-Type": "application/json",
    }


def _anthropic_headers(key):
    return {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def _openai_payload(model, system, user, reasoning_effort):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    override = _temperature_override()
    if override is not None:
        payload["temperature"] = override
    return payload


def _anthropic_payload(model, system, user):
    return {
        "model": model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": sampling_settings("anthropic")["temperature"],
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }


def _openai_text(body):
    """Chat Completions: choices[0].message.content (string). A refusal is an
    adapter error that carries the refusal text."""
    choices = body.get("choices") or []
    if not choices:
        raise AdapterError("openai response missing choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        # Defensive: content parts [{"type": "text", "text": ...}].
        content = "".join(part.get("text", "") for part in content
                          if isinstance(part, dict) and part.get("type") in {"text", "output_text"})
    if not isinstance(content, str) or not content:
        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal:
            raise AdapterError("openai refusal: %s" % refusal[:200])
        raise AdapterError("openai response missing text (finish_reason=%s)" % choices[0].get("finish_reason"))
    return content


def _anthropic_text(body):
    """Messages API: concatenate every ``text`` block; ignore other block types."""
    blocks = body.get("content") or []
    texts = [block.get("text") for block in blocks
             if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)]
    if not texts:
        raise AdapterError("anthropic response missing text (stop_reason=%s)" % body.get("stop_reason"))
    return "".join(texts)


def _usage_from(body, provider):
    usage = body.get("usage") or {}
    if provider == "openai":
        return Usage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            retries=0,
        )
    return Usage(
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        retries=0,
    )


def _reported_model(body, requested):
    reported = body.get("model")
    if isinstance(reported, str) and reported:
        return reported
    return requested


class ModelClient:
    def __init__(self, provider, transport=None, budget=None):
        if provider not in ALLOWED_MODELS:
            raise ProviderConfigError("unknown provider")
        self.provider = provider
        self.model = pinned_model(provider)
        self.transport = transport or HttpTransport()
        self.budget = budget

    def complete(self, system, user):
        require_live()
        ticket = None
        if self.budget is not None:
            from ..budget import prompt_token_bound
            ticket = self.budget.reserve(
                input_tokens=prompt_token_bound(system, user),
                output_tokens=MAX_OUTPUT_TOKENS,
            )
        try:
            key = _api_key(self.provider)
            if self.provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                headers = _openai_headers(key)
                payload = _openai_payload(self.model, system, user, _openai_effort())
            else:
                url = "https://api.anthropic.com/v1/messages"
                headers = _anthropic_headers(key)
                payload = _anthropic_payload(self.model, system, user)
            status, body = self.transport.post(url, headers, payload)
            if status != 200 or not isinstance(body, dict):
                raise AdapterError("provider returned %s" % status)
            reported = _reported_model(body, self.model)
            if self.provider == "openai" and not openai_served_ok(reported):
                raise ProviderConfigError("openai served %r instead of gpt-6-luna" % reported)
            if self.provider == "anthropic" and "haiku-4-5" not in reported:
                raise ProviderConfigError("anthropic served %r instead of Haiku 4.5" % reported)
            text = _openai_text(body) if self.provider == "openai" else _anthropic_text(body)
            usage = _usage_from(body, self.provider)
            if ticket is not None:
                self.budget.settle(ticket, usage)
            return text, usage, reported
        except Exception:
            if ticket is not None and ticket.get("status") == "pending":
                self.budget.fail(ticket, "request failed; reservation retained")
            raise


class ModelActor:
    """Actor that asks a pinned model for one JSON action per observation."""

    def __init__(self, role, provider, prompt, transport=None, budget=None):
        self.role = role
        self.prompt = prompt
        self.client = ModelClient(provider, transport=transport, budget=budget)
        self.last_reported_model = None
        self.last_usage = None
        self.last_raw = None
        self.last_error = None

    def decide(self, observation):
        user = json.dumps({"observation": observation, "contract": ACTION_CONTRACT}, sort_keys=True)
        self.last_raw = self.last_error = self.last_usage = None
        raw_text, usage, reported = self.client.complete(self.prompt + "\n" + ACTION_CONTRACT, user)
        self.last_reported_model = reported
        self.last_usage = usage
        self.last_raw = raw_text
        return _decision_from(self, raw_text, usage)


def _decision_from(actor, raw_text, usage):
    """Parse a reply; on failure keep the exact reason on the actor and re-raise."""
    try:
        raw = _extract_json_object(raw_text)
        action, arguments = parse_decision(raw)
    except AdapterError as exc:
        actor.last_error = str(exc)
        raise
    return Decision(action, arguments, raw, usage)


def describe_setup():
    """Local diagnostics. Does not perform a network call."""
    rows = []
    for provider in ("openai", "anthropic"):
        try:
            model = pinned_model(provider)
            model_ok = True
            error = None
        except ProviderConfigError as exc:
            model = os.environ.get(MODEL_ENV[provider], DEFAULT_MODELS[provider])
            model_ok = False
            error = str(exc)
        rows.append({
            "provider": provider,
            "model": model,
            "model_allowed": model_ok,
            "key_present": bool(os.environ.get(KEY_ENV[provider], "").strip()),
            "live_calls_allowed": live_calls_allowed(),
            "error": error,
        })
    return {
        "claim": "Provider setup only. No network call. No key values.",
        "providers": rows,
    }


if __name__ == "__main__":
    from .provider_report import write_setup_report
    report = write_setup_report()
    print(json.dumps(report, indent=2, sort_keys=True))
