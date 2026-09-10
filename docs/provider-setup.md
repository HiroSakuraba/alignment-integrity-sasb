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

The dry-run prints whether each key is present and which model is pinned. It does not call the network.

Live calls also require both of:

```sh
export SASB_ENABLE_NETWORK=1
export SASB_PROVIDER_VALIDATED=1
```

Leave those unset until the dry-run shows the pinned models. `make test` stays scripted either way.

The maintenance matrix is not yet wired to `ModelActor`. This client is the boundary that a later Stage B cell can attach.
