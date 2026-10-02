"""Realistic provider response fixtures for the live adapter path.

Shapes follow the public Anthropic Messages API (``type: message`` with
``content`` text blocks, ``stop_reason``, cache usage fields) and OpenAI Chat
Completions (``object: chat.completion``, ``message.refusal``, ``annotations``,
token detail objects). No network is used.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from sasb.agents.adapters import AdapterError, parse_decision
from sasb.agents.providers import (
    ACTION_CONTRACT,
    ANTHROPIC_MODEL,
    OPENAI_MODEL,
    ModelActor,
    ModelClient,
    _extract_json_object,
)
from sasb.live import run_experiment
from sasb.transcript import ReplayIndex, load


def anthropic_message(text, input_tokens=489, output_tokens=36, stop_reason="end_turn", model=ANTHROPIC_MODEL):
    return {
        "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text, "citations": None}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "container": None,
        "usage": {
            "input_tokens": input_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0},
            "output_tokens": output_tokens,
            "service_tier": "standard",
        },
    }


def openai_completion(text, prompt_tokens=435, completion_tokens=18, model=OPENAI_MODEL,
                      refusal=None, finish_reason="stop"):
    return {
        "id": "chatcmpl-CJ5bW2v0nZ9Kx1rE7Yy3",
        "object": "chat.completion",
        "created": 1790960900,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text, "refusal": refusal, "annotations": []},
            "logprobs": None,
            "finish_reason": finish_reason,
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_tokens_details": {"cached_tokens": 0, "audio_tokens": 0},
            "completion_tokens_details": {
                "reasoning_tokens": 0, "audio_tokens": 0,
                "accepted_prediction_tokens": 0, "rejected_prediction_tokens": 0,
            },
        },
        "service_tier": "default",
        "system_fingerprint": None,
    }


class SequenceTransport:
    """Returns one canned body per request, then repeats the last."""

    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.capture = []

    def post(self, url, headers, payload, timeout=30):
        self.capture.append({"url": url, "payload": payload})
        index = min(len(self.capture) - 1, len(self.bodies) - 1)
        return 200, json.loads(json.dumps(self.bodies[index]))


INSPECT = '{"action": "inspect_resource", "arguments": {"tenant": "tenant_a"}}'

VALID_REPLIES = {
    "compact": '{"action":"inspect_resource","arguments":{"tenant":"tenant_a"}}',
    "pretty": '{\n  "action": "inspect_resource",\n  "arguments": {\n    "tenant": "tenant_a"\n  }\n}',
    "json_fence": "```json\n" + INSPECT + "\n```",
    "bare_fence": "```\n" + INSPECT + "\n```",
    "upper_fence_crlf": "```JSON\r\n" + INSPECT + "\r\n```",
    "fence_with_prose": "I'll inspect the resource first.\n\n```json\n" + INSPECT + "\n```\n\nThis confirms ownership.",
    "prose_then_object": "Action: " + INSPECT,
    "whitespace": "\n\n   " + INSPECT + "   \n",
    "bom": "\ufeff" + INSPECT,
    "unterminated_fence": "```json\n" + INSPECT,
    "empty_arguments": '{"action": "inspect_resource", "arguments": {}}',
    "missing_arguments": '{"action": "inspect_resource"}',
}

NOOP_REPLIES = {
    "noop_empty": '{"action": "noop", "arguments": {}}',
    "noop_null": '{"action": "noop", "arguments": null}',
    "noop_missing": '{"action": "noop"}',
}

MALFORMED_REPLIES = {
    "not_json": ("I will inspect the resource.", "not a JSON object"),
    "truncated": ('{"action": "inspect_resource", "arguments": {"tenant": "ten', "invalid JSON action"),
    "two_objects": (INSPECT + "\n" + '{"action": "noop", "arguments": {}}', "more than one JSON object"),
    "two_fences": ("```json\n" + INSPECT + "\n```\n```json\n{}\n```", "2 code blocks"),
    "unknown_action": ('{"action": "write_db", "arguments": {}}', "unknown action 'write_db'"),
    "extra_top_level": ('{"action": "noop", "arguments": {}, "reasoning": "x"}', "unexpected top-level fields ['reasoning']"),
    "invented_argument": ('{"action": "inspect_resource", "arguments": {"tenant": "tenant_a", "resource": "test-db"}}',
                          "unexpected=['resource']"),
    "missing_required": ('{"action": "stop", "arguments": {}}', "missing=['reason']"),
    "null_required": ('{"action": "stop", "arguments": null}', "missing=['reason']"),
    "empty_value": ('{"action": "stop", "arguments": {"reason": "  "}}', "nonempty strings: ['reason']"),
    "number_value": ('{"action": "inspect_resource", "arguments": {"tenant": 7}}', "nonempty strings: ['tenant']"),
    "arguments_list": ('{"action": "noop", "arguments": []}', "arguments must be an object"),
    "duplicate_key": ('{"action": "noop", "action": "stop", "arguments": {}}', "duplicate JSON field 'action'"),
    "nan": ('{"action": "noop", "arguments": {"x": NaN}}', "non-finite"),
    "empty": ("   ", "empty model output"),
}


def _parse(text):
    return parse_decision(_extract_json_object(text))


class ReplyParsingTests(unittest.TestCase):
    def test_contract_lists_argument_names_from_parser_table(self):
        for fragment in ("inspect_resource {tenant?}", "complete_maintenance {resource?}",
                         "use_credential {credential, resource}", "noop {}", "stop {reason}",
                         "Use only these argument names", "Use {} for an action that needs no arguments"):
            self.assertIn(fragment, ACTION_CONTRACT)

    def test_valid_replies_parse(self):
        for name, text in VALID_REPLIES.items():
            with self.subTest(name=name):
                action, arguments = _parse(text)
                self.assertEqual(action, "inspect_resource")
                self.assertIn(arguments, ({"tenant": "tenant_a"}, {}))

    def test_empty_arguments_for_actions_that_take_none(self):
        for name, text in NOOP_REPLIES.items():
            with self.subTest(name=name):
                self.assertEqual(_parse(text), ("noop", {}))

    def test_malformed_replies_are_adapter_errors_with_exact_reason(self):
        for name, (text, reason) in MALFORMED_REPLIES.items():
            with self.subTest(name=name):
                with self.assertRaises(AdapterError) as ctx:
                    _parse(text)
                self.assertIn(reason, str(ctx.exception))


class _LiveEnv(unittest.TestCase):
    def setUp(self):
        os.environ["SASB_ENABLE_NETWORK"] = "1"
        os.environ["SASB_PROVIDER_VALIDATED"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        os.environ["OPENAI_API_KEY"] = "sk-test-openai"
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()
        for key in ("SASB_ENABLE_NETWORK", "SASB_PROVIDER_VALIDATED", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            os.environ.pop(key, None)


class ProviderFixtureTests(_LiveEnv):
    def test_realistic_bodies_through_client_and_actor(self):
        cases = [
            ("anthropic", anthropic_message("```json\n" + INSPECT + "\n```")),
            ("anthropic", anthropic_message(INSPECT, model="claude-haiku-4-5")),
            ("openai", openai_completion(INSPECT)),
            ("openai", openai_completion("```json\n" + INSPECT + "\n```", model="gpt-6-luna-2026-09-01")),
        ]
        for provider, body in cases:
            with self.subTest(provider=provider, model=body["model"]):
                actor = ModelActor("worker", provider, "be terse", transport=SequenceTransport([body]))
                decision = actor.decide({"task": "t"})
                self.assertEqual((decision.action, decision.arguments), ("inspect_resource", {"tenant": "tenant_a"}))
                self.assertGreater(decision.usage.input_tokens, 400)
                self.assertGreater(decision.usage.output_tokens, 0)
                self.assertEqual(actor.last_raw, body["content"][0]["text"] if provider == "anthropic"
                                 else body["choices"][0]["message"]["content"])

    def test_anthropic_multiple_text_blocks_are_joined(self):
        body = anthropic_message("")
        body["content"] = [{"type": "text", "text": '{"action": "noop",', "citations": None},
                           {"type": "text", "text": ' "arguments": {}}', "citations": None}]
        client = ModelClient("anthropic", transport=SequenceTransport([body]))
        text, _, _ = client.complete("s", "u")
        self.assertEqual(_parse(text), ("noop", {}))

    def test_openai_refusal_is_adapter_error_with_reason(self):
        body = openai_completion(None, refusal="I can't help with that.")
        actor = ModelActor("worker", "openai", "p", transport=SequenceTransport([body]))
        with self.assertRaisesRegex(AdapterError, "openai refusal: I can't help with that."):
            actor.decide({})

    def test_actor_keeps_raw_and_reason_on_parse_failure(self):
        text = '{"action": "inspect_resource", "arguments": {"tenant": "tenant_a", "resource": "test-db"}}'
        actor = ModelActor("worker", "anthropic", "p", transport=SequenceTransport([anthropic_message(text)]))
        with self.assertRaises(AdapterError):
            actor.decide({})
        self.assertEqual(actor.last_raw, text)
        self.assertIn("unexpected=['resource']", actor.last_error)
        self.assertEqual(actor.last_usage.input_tokens, 489)


class TranscriptOnErrorTests(_LiveEnv):
    def _run(self, provider, body):
        transcript = Path(self.tmp.name) / ("%s.jsonl" % provider)
        transport = SequenceTransport([body])
        report = run_experiment(provider=provider, dry_run=False, mode="worker", transport=transport,
                                conditions=("authorized_maintenance",), roles=("honest",),
                                cap_usd=0.5, transcript_path=str(transcript))
        header, episodes = load(transcript)
        return report, transport, header, episodes

    def test_adapter_error_turn_records_raw_usage_and_reason(self):
        text = '```json\n{"action": "inspect_resource", "arguments": {"tenant": "tenant_a", "resource": "test-db"}}\n```'
        for provider, body, tokens in (("anthropic", anthropic_message(text), (489, 36)),
                                       ("openai", openai_completion(text), (435, 18))):
            with self.subTest(provider=provider):
                report, transport, header, episodes = self._run(provider, body)
                self.assertEqual(len(transport.capture), 1, "adapter errors are not retried")
                turn = episodes[0]["turns"][0]
                self.assertEqual(turn["error"], "adapter_error")
                self.assertEqual(turn["raw_response"], text)
                self.assertIsNone(turn["parsed_json"])
                self.assertEqual(turn["usage"]["input_tokens"], tokens[0])
                self.assertEqual(turn["usage"]["output_tokens"], tokens[1])
                self.assertIn("missing or unexpected action arguments for inspect_resource", turn["error_reason"])
                self.assertIn("unexpected=['resource']", turn["error_reason"])
                self.assertIn("Use only these argument names", turn["system_prompt"])
                self.assertEqual(header["action_contract"], ACTION_CONTRACT)
                self.assertTrue(report["rows"][0]["invalid_action_or_actor_error"])

    def test_fenced_valid_reply_runs_the_episode(self):
        replies = [anthropic_message("```json\n" + INSPECT + "\n```"),
                   anthropic_message('{"action": "complete_maintenance", "arguments": {}}'),
                   anthropic_message('```json\n{"action": "noop", "arguments": {}}\n```')]
        transcript = Path(self.tmp.name) / "seq.jsonl"
        transport = SequenceTransport(replies)
        report = run_experiment(provider="anthropic", dry_run=False, mode="worker", transport=transport,
                                conditions=("authorized_maintenance",), roles=("honest",),
                                cap_usd=0.5, transcript_path=str(transcript))
        row = report["rows"][0]
        self.assertFalse(row["invalid_action_or_actor_error"])
        self.assertTrue(row["authorized_task_completion"])
        self.assertFalse(row["completed_violation"])
        _, episodes = load(transcript)
        turns = [t for t in episodes[0]["turns"] if t["agent_id"] == "worker-1"]
        self.assertEqual(turns[0]["raw_response"], "```json\n" + INSPECT + "\n```")
        self.assertEqual(json.loads(turns[0]["parsed_json"]), json.loads(INSPECT))
        self.assertEqual(turns[1]["action"], "complete_maintenance")
        self.assertTrue(all(t["usage"]["input_tokens"] == 489 for t in turns))
        self.assertTrue(all(t.get("error") is None for t in turns))

    def test_error_transcript_replays_without_network(self):
        text = "Sure! I'll inspect first."
        self._run("anthropic", anthropic_message(text))
        index = ReplayIndex(Path(self.tmp.name) / "anthropic.jsonl")
        actors = index.actors("authorized_maintenance", "honest", "proposed", "worker")
        with self.assertRaisesRegex(AdapterError, "not a JSON object"):
            actors["worker-1"].decide({})


if __name__ == "__main__":
    unittest.main()
