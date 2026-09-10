import json
import os
import unittest

from sasb.agents.adapters import AdapterError
from sasb.agents.providers import (
    ANTHROPIC_MODEL,
    OPENAI_MODEL,
    ModelActor,
    ModelClient,
    ProviderConfigError,
    ProviderDisabled,
    describe_setup,
    live_calls_allowed,
    pinned_model,
    require_live,
)


class FakeTransport:
    def __init__(self, status=200, body=None, capture=None):
        self.status = status
        self.body = body or {}
        self.capture = capture if capture is not None else []

    def post(self, url, headers, payload, timeout=30):
        self.capture.append({"url": url, "headers": headers, "payload": payload})
        return self.status, self.body


def _openai_body(text='{"action":"noop","arguments":{}}', model=OPENAI_MODEL):
    return {
        "model": model,
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
    }


def _anthropic_body(text='{"action":"stop","arguments":{"reason":"done"}}', model=ANTHROPIC_MODEL):
    return {
        "model": model,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 9, "output_tokens": 3},
    }


class ProviderGateTests(unittest.TestCase):
    def test_disabled_by_default(self):
        os.environ.pop("SASB_ENABLE_NETWORK", None)
        os.environ.pop("SASB_PROVIDER_VALIDATED", None)
        self.assertFalse(live_calls_allowed())
        with self.assertRaises(ProviderDisabled):
            require_live()

    def test_both_flags_required(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ.pop("SASB_PROVIDER_VALIDATED", None)
        self.assertFalse(live_calls_allowed())
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ.pop("SASB_ENABLE_NETWORK", None)
        self.assertFalse(live_calls_allowed())


class PinTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SASB_OPENAI_MODEL", None)
        os.environ.pop("SASB_ANTHROPIC_MODEL", None)

    def test_default_pins(self):
        os.environ.pop("SASB_OPENAI_MODEL", None)
        os.environ.pop("SASB_ANTHROPIC_MODEL", None)
        self.assertEqual(pinned_model("openai"), OPENAI_MODEL)
        self.assertEqual(pinned_model("anthropic"), ANTHROPIC_MODEL)

    def test_rejects_sol_and_sonnet(self):
        os.environ["SASB_OPENAI_MODEL"] = "gpt-5.6-sol"
        with self.assertRaises(ProviderConfigError):
            pinned_model("openai")
        os.environ["SASB_ANTHROPIC_MODEL"] = "claude-sonnet-5"
        with self.assertRaises(ProviderConfigError):
            pinned_model("anthropic")

    def test_haiku_alias_allowed(self):
        os.environ["SASB_ANTHROPIC_MODEL"] = "claude-haiku-4-5"
        self.assertEqual(pinned_model("anthropic"), "claude-haiku-4-5")


class ClientTests(unittest.TestCase):
    def setUp(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["OPENAI_API_KEY"] = "sk-test-openai"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"

    def tearDown(self):
        for key in (
            "SASB_ENABLE_NETWORK",
            "SASB_PROVIDER_VALIDATED",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "SASB_OPENAI_MODEL",
            "SASB_ANTHROPIC_MODEL",
            "SASB_OPENAI_REASONING_EFFORT",
        ):
            os.environ.pop(key, None)

    def test_openai_payload_pins_luna(self):
        capture = []
        client = ModelClient("openai", transport=FakeTransport(body=_openai_body(), capture=capture))
        text, usage, reported = client.complete("sys", "user")
        self.assertEqual(capture[0]["payload"]["model"], OPENAI_MODEL)
        self.assertEqual(reported, OPENAI_MODEL)
        self.assertEqual(usage.input_tokens, 12)
        self.assertIn("action", text)

    def test_rejects_openai_upgrade(self):
        body = _openai_body(model="gpt-5.6-terra")
        client = ModelClient("openai", transport=FakeTransport(body=body))
        with self.assertRaises(AdapterError):
            client.complete("sys", "user")

    def test_rejects_anthropic_upgrade(self):
        body = _anthropic_body(model="claude-sonnet-5")
        client = ModelClient("anthropic", transport=FakeTransport(body=body))
        with self.assertRaises(AdapterError):
            client.complete("sys", "user")

    def test_actor_parses_fenced_json(self):
        fenced = "```json\n{\"action\":\"noop\",\"arguments\":{}}\n```"
        actor = ModelActor("worker", "openai", "be terse", transport=FakeTransport(body=_openai_body(fenced)))
        decision = actor.decide({"task": "maintain"})
        self.assertEqual(decision.action, "noop")
        self.assertEqual(actor.last_reported_model, OPENAI_MODEL)

    def test_actor_invalid_json_is_adapter_error(self):
        actor = ModelActor(
            "worker",
            "anthropic",
            "be terse",
            transport=FakeTransport(body=_anthropic_body("sure, I will help")),
        )
        with self.assertRaises(AdapterError):
            actor.decide({})

    def test_describe_setup_omits_key_values(self):
        report = describe_setup()
        blob = json.dumps(report)
        self.assertNotIn("sk-test-openai", blob)
        self.assertNotIn("sk-ant-test", blob)
        self.assertTrue(report["providers"][0]["key_present"])


class IsolatedGateTests(unittest.TestCase):
    def test_client_respects_gate_even_with_key(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-openai"
        os.environ.pop("SASB_ENABLE_NETWORK", None)
        os.environ.pop("SASB_PROVIDER_VALIDATED", None)
        client = ModelClient("openai", transport=FakeTransport(body=_openai_body()))
        with self.assertRaises(ProviderDisabled):
            client.complete("sys", "user")
        os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
