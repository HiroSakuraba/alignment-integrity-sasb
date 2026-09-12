# Provider setup (Luna and Haiku only)

Do not paste API keys into git, issues, or episode records.

## Allowed models

| Provider | Model id |
| --- | --- |
| OpenAI | `gpt-5.6-luna` |
| Anthropic | `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`) |

Any other id, including Sol, Terra, Sonnet, and Opus, is rejected before the request and again if the provider response names a different model.

## Local config

```sh
cp .env.example .env
# edit .env: set OPENAI_API_KEY and ANTHROPIC_API_KEY
python3 -m sasb.agents.providers
```

The command prints a readiness report and writes `reports/provider-setup-local.json` (gitignored). It records pins, gate flags, key presence, the request contract, and next steps. It does not call the network and does not store key values.

Live calls also require both of:

```sh
export SASB_ENABLE_NETWORK=1
export SASB_PROVIDER_VALIDATED=1
```

Leave those unset until the dry-run shows the pinned models. `make test` stays scripted either way.

```sh
python3 -m sasb.live --dry-run --mode worker --cap-usd 1.00
```

That command runs the Stage B driver against scripted policies and writes
`reports/live-run-local.json` (gitignored). It does not call the network.
A paid worker cell still needs both flags:

```sh
export SASB_ENABLE_NETWORK=1
export SASB_PROVIDER_VALIDATED=1
python3 -m sasb.live --provider anthropic --mode worker --cap-usd 1.00
```

The frozen Stage A reports are unchanged. Cost is reported usage against the
pinned Luna/Haiku rates, not a 12k-token assumption.

Paid runs write `reports/live-run-paid.json` and checkpoint after every cell so
a crash does not drop the ledger. Dry-run still writes
`reports/live-run-local.json` and includes `forecast_usd_if_paid`.

Under the proposed runtime the scripted noncompliant worker cannot complete a
violation, so adversary cells are skipped unless `--pay-unreachable`. Honest
cells are always paid: that is the false-refusal measurement. Use
`--runtime default` when you want reachable-harm adversary cells.

`--fake-transport` sends a stub 200 through the real `ModelActor` without
opening a socket. It still requires the two live flags.

## Paid wrapper

See [paid-run.md](paid-run.md) for the reservation ledger, local lock, no-overwrite rule, and the manual Actions workflow. `python3 -m sasb.pilot` calls `sasb.live`; it does not define a second experiment matrix.
