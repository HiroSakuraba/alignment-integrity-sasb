# Luna and Haiku pilot

The regular test suite and Stage A workflow make no model API calls. The separate
pilot connects a worker to the synthetic maintenance service. It does not run a
swarm, train a model, or establish a safety improvement.

## Models and limits

| Setting | Pilot value |
| --- | --- |
| OpenAI model | `gpt-5.6-luna` |
| Anthropic model | `claude-haiku-4-5-20251001` |
| Luna reasoning | `none` |
| Haiku extended thinking | Off |
| Output allowance | 256 tokens per request |
| Input allowance | 12,000 UTF-8 bytes of system and user text per request |
| Requests | At most 34 across both providers |
| Cost allowance | $0.50 estimated per run; local maximum $1 |
| Retries | None |

Other model families are rejected; no automatic upgrade or fallback is available.
The connection checks validate actual response model IDs, token usage, and JSON
before episodes begin. Haiku's `claude-haiku-4-5` alias is also accepted.

The pilot makes one connection check per provider, then eight worker episodes:
two conditions (authorized maintenance and tempting unauthorized credentials),
two runtime treatments (default and proposed), and two providers. Each episode
allows four actions. Provider order is fixed and there is one observation per
cell; this is an integration pilot, not a statistically powered comparison.
Malformed actions stay in the results. Unstarted cells must not be counted as
successful episodes. Peer content is fixed fixture text; there are no live peer
agents. The existing scorer is reused without changing its metric definitions.

## GitHub setup

In this repository, open **Settings → Secrets and variables → Actions → New
repository secret**. Add `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` separately.
Never put values in source files, workflow inputs, issues, or chat.

After the pilot workflow is merged into `main`, open **Actions → SASB small paid
pilot → Run workflow**. Select `main`, check the paid-run confirmation, and run
it once. Offline checks run first. Keys are passed only to the paid step. Pushes
and pull requests cannot trigger this workflow. Its concurrency group prevents
overlapping pilots, but each manually requested run has a fresh budget.

Download the `sasb-pilot-<run>-<attempt>` artifact for results and the request
ledger. Cancellation or abrupt runner termination can leave an in-flight request
marked pending; reconcile that request against provider usage before another
run. Do not automatically rerun failed jobs.

## Local setup

```sh
cp .env.example .env
# Edit .env locally and enter the two keys.
python3 -m sasb.agents.providers
python3 -m sasb.pilot
```

Both commands load `.env` and make zero network calls. The loader accepts literal
`KEY=value` lines, optional matching quotes, blank lines, and full-line comments.
It never evaluates shell commands. Existing environment variables take priority.
The ignored `.env` file is plain text on your machine; protect access to it.

For an explicitly intended paid pilot:

```sh
export SASB_ENABLE_NETWORK=1
export SASB_PROVIDER_VALIDATED=1
python3 -m sasb.pilot --live --budget-usd 0.50 --output reports/pilot-local.json
```

The CLI refuses to overwrite an existing output. Keep both switches off outside
paid runs. The `--live` argument is also required even if both switches are set.
`SASB_PROVIDER_VALIDATED` authorizes the validation attempt; a local dry run does
not prove that a provider account has access. The connection checks do that.

## Spending and failure accounting

A shared serial ledger reserves estimated cost before each HTTP request and
checkpoints the report to disk before sending. Input reservations use UTF-8 byte
length plus 4,096 tokens for protocol overhead; output reservations use 256
tokens. Requests exceeding the input, request-count, or remaining cost allowance
are rejected before transport. The client timeout is 30 seconds, with a 40-second
session deadline. A timeout does not prove the provider stopped generating.

Token usage is settled before parsing action JSON. Malformed actions therefore
retain their paid usage in the ledger even when session-level usage is absent.
Missing usage, timeouts, or transport errors retain a reservation and stop further
requests. Unexpected models and malformed provider envelopes also stop the run.
Reports keep completed and failed episodes, prompt hashes, commit ID, decoding
settings, exact observations, decisions, receipts, and per-request usage. Keys and
HTTP headers are excluded. Inspect reports before sharing: observations and model
output are saved, though this pilot uses only synthetic task data.

Rates checked on 2026-09-10: Luna $0.20 input / $1.20 output and Haiku $1 input /
$5 output per million tokens. The ledger uses a 25% input margin, including cached
inputs, rather than claiming cache savings. Recheck rates before reuse. This is
an enforced local estimate, **not an exact provider billing cap**: pricing changes,
provider token accounting, other applications, and separate runs are outside it.
Use provider account spending controls as an additional limit.

Official references:
- https://developers.openai.com/api/docs/models/gpt-5.6-luna
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- https://platform.claude.com/docs/en/models/overview
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
