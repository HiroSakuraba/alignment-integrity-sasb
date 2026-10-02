# Paid run (local estimate, not a billing cap)

This is not a second experiment. `sasb.live` still owns cells, reachability,
honest-pay, transcripts, and checkpoints. The reservation ledger is a
single-use spend permit in front of each HTTP request.

## Why this exists

The previous budget pilot duplicated the driver and reserved after a whole
cell. A worker episode can issue several model calls. Checking the dollar cap
only after the episode can overshoot. A request with no usage field can also
be treated as free unless the reservation is retained.

The rule is the same as other Stage A controls: a consequential action does
not leave the machine without a current permit.

## What the ledger does

1. Before `transport.post`, reserve the most the request can cost at the
   pinned Luna/Haiku rate card: an upper bound on its prompt tokens (UTF-8
   bytes of the exact system + user text, plus 32 framing tokens) and its max
   output tokens (256). Both providers use byte-level BPE tokenizers, so a token
   covers at least one byte and the bound cannot under-count. Cache discounts
   are never assumed. Amounts round up to the micro-dollar. The reservation is
   granted only if it fits under the cap after everything already accounted,
   so the local ledger can never exceed `cap_usd`. Prompts above 100k tokens
   are refused (keeps clear of long-context price tiers).
2. After a 200 with token usage, settle to the actual estimate and release
   unused reserve. If reported usage ever exceeded the reservation, the real
   amount is accounted and later requests are blocked.
3. If usage is missing, the HTTP call fails, or the served model is rejected,
   keep the reservation and block later requests.
4. `cap_usd <= 0` is a hard stop: no actor is built and no transport is used.
5. A local `fcntl` lock and a fresh output path stop two processes from
   writing the same paid report.

These numbers are not the provider invoice.

## Commands

Dry rehearsal, no keys:

```sh
python3 -m sasb.live --dry-run --mode worker --cap-usd 1.00
```

Fake transport through the real client (still needs the two live flags):

```sh
export SASB_ENABLE_NETWORK=1
export SASB_PROVIDER_VALIDATED=1
python3 -m sasb.live --provider anthropic --fake-transport --mode worker --cap-usd 0.50
```

Bounded paid wrapper (default cap $0.50, refuses to overwrite). `--provider`
is required; there is no default provider:

```sh
python3 -m sasb.pilot --provider anthropic --mode worker --cap-usd 0.50
```

`--force` overwrites an existing `--out` and transcript. `--lock` defaults to
`reports/live-run.lock`. The full transcript is written next to the report
as `<out stem>.transcript.jsonl` (for the default `--out`,
`reports/live-run-paid.transcript.jsonl`). One header line, then one line per
episode with every turn: for model turns the exact `system_prompt` and
`user_prompt` sent, the `raw_response`, the parsed action, arguments, usage and
error status, plus receipts and the score. API keys are never written.
Replay it for free with `python3 -m sasb.live --replay <transcript>`.

## Live run from GitHub Actions

Workflow **SASB paid wrapper (manual)** (`.github/workflows/sasb-paid.yml`) is
`workflow_dispatch` only. It always runs the offline suite first; the pilot job
only starts if that passes and `confirm` is `PAY`.

| Input | Fake rehearsal (no spend) | Real paid run |
| --- | --- | --- |
| `confirm` | `PAY` | `PAY` |
| `provider` | `anthropic` or `openai` | `anthropic` or `openai` (the `choose` placeholder fails the run) |
| `fake` | ticked (default) | **unticked** |
| `cap_usd` | `0.50` | `0.50` (accepted range 0 to 5.00) |

Setup: add the repository secret for the provider you will select
(`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, Settings > Secrets and variables >
Actions). With `fake` unticked the job fails before any request with a clear
error if that secret is missing or empty; only the selected provider's secret
is passed to the job, and its value is never printed. With `fake` ticked no
secret is read and `--fake-transport` is passed. The artifact
`sasb-paid-<provider>-<fake|live>-<run id>` contains
`reports/live-run-paid.json` and `reports/live-run-paid.transcript.jsonl`.
Runs are serialized by a workflow `concurrency` group.

Models a real run uses (pinned; any other served model is rejected):

| Provider | Model | Rate (USD per 1M tokens, input / output) |
| --- | --- | --- |
| `anthropic` | `claude-haiku-4-5-20251001` | 1.00 / 5.00 |
| `openai` | `gpt-6-luna` (a dated `gpt-6-luna-YYYY-MM-DD` echo is accepted) | 0.10 / 0.50 |

Expected cost of a worker-mode run under the proposed runtime (5 honest
episodes, up to 6 worker requests each = 30 requests; adversary cells are
unreachable and skipped). The fake transport reports a fixed 24 input / 8
output tokens per request, so its 720 / 240 totals understate real prompts:
the actual prompts are 1.9 to 2.5 KB, about 430 to 580 tokens each.

| | Haiku 4.5 | GPT-6 Luna |
| --- | --- | --- |
| Fake-run token totals (720 in / 240 out) priced literally | $0.0019 | $0.0002 |
| Realistic (~15.5k to 20k in, ~0.5k to 1.8k out) | ~$0.02 to $0.03 | ~$0.002 to $0.003 |
| Hard ceiling (every byte a token, 256 output tokens on all 30) | $0.11 | $0.011 |
| Per-request reservation | ~$0.0032 to $0.0038 | ~$0.00032 to $0.00038 |

A $0.50 cap therefore does not bind; the run stops at `episode_cap`.

## What this is not

- Not a Stage B measurement.
- Not a swarm experiment unless `--mode swarm` and extra `model_roles`.
- Not a claim that the local estimate matches the bill.
- Not enabled in ordinary CI. The optional paid workflow is manual and starts
  with the offline suite.
