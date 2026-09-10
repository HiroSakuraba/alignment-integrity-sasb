# Project entry point

This repository is a Stage A scripted harness. It is not evidence about frontier-model behavior.

Read, in order:

1. `README.md` for scope and claims.
2. `docs/research-framework.html` for the research program.
3. `docs/threat-model.md` before changing a trust boundary.
4. `docs/experiment-protocol.md` before adding a provider or training code.
5. `docs/HISTORICAL_NO_GO_LEDGER.md` before reviving an abandoned direction.

Run `make test` and `make verify` before and after a change.

## Load-bearing invariants

- Evaluator-only fields listed in `sasb.runtime.spaces.FORBIDDEN_AGENT_FIELDS` cannot be published as observations.
- Delegation cannot expand the delegator's permissions.
- A peer message is not a permission-service update.
- Unauthorized attempts and completed effects are scored separately.
- Network providers stay disabled by default.

## Change rules

Do not weaken an invariant to make an experiment easier. Add an explicit unsafe fixture instead. Do not commit API keys. Do not train on condemned transcripts as desired completions.
