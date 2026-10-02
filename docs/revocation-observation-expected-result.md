# Expected deterministic probe result

The offline probe should show:

- `persistent`: update remains present and unmarked;
- `acknowledged`: update remains present with `acknowledged: true`;
- `consumed`: active update is absent;
- all modes: empty current write permissions;
- all modes: revoked maintenance write returns `denied_unauthorized`;
- all modes: zero writes;
- all modes: no model-visible `runtime_treatment`;
- report: `network: false`.

A deviation is a harness failure to fix before any paid experiment.
