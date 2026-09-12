# Paid live wrapper

`sasb.live` remains the experiment driver. `sasb.pilot` only adds spending
controls around that driver. It is not a second matrix and it does not change
Stage A reports.

## What is new

1. Reserve an estimated cell cost against pinned Luna/Haiku rates before a
   paid episode. Missing usage keeps the reservation and blocks later calls.
2. A `$0` cap is a hard no-request contract. The first cell is not an exception.
3. Local paid runs take `reports/live-run.lock` and refuse to overwrite
   `reports/live-run-paid.json` unless `--force` is passed.
4. The optional GitHub workflow runs only on `main` after an explicit confirm
   box. Ordinary `make test` stays offline.

The ledger is a local estimate with a 25% input margin. It is not a provider
billing cap. Use account spending limits as a second control. Do not start a
local `--live` process at the same time as the Actions workflow; each has its
own estimate.

## Commands

```sh
python3 -m sasb.live --dry-run --mode worker
python3 -m sasb.live --fake-transport --provider anthropic --mode worker --cap-usd 0.50
python3 -m sasb.pilot --provider anthropic --mode worker --cap-usd 0.50
```

`--fake-transport` still requires the two live flags. It does not open a
socket. Honest cells remain paid when a violation is unreachable. Adversary
cells on the proposed runtime stay skipped unless `--pay-unreachable`.
