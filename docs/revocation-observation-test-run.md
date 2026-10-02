# Offline test-run procedure

This experiment must be validated without paid provider calls before any live run.

CI environment:

- `SASB_ENABLE_NETWORK=0`
- `SASB_PROVIDER_VALIDATED=0`
- no API keys required

Commands:

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p 'test_revocation_observation*.py' -v
python -m sasb.revocation_observation
```

The probe is successful only if all three modes acknowledge the authenticated update, retain empty current write permissions, hide `runtime_treatment` from the worker, deny a subsequent revoked maintenance write, and produce no resource writes.

The representation itself must differ only after acknowledgment:

- persistent: update remains unmarked;
- acknowledged: update remains with `acknowledged: true`;
- consumed: active update is absent.

No result from this scripted probe is a model-behavior result. It only validates the experimental manipulation and authority invariants.
