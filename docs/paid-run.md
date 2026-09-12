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

1. Before `transport.post`, reserve a conservative estimate from the pinned
   Luna/Haiku rate card. Input tokens are padded. Cache discounts are never
   assumed.
2. After a 200 with token usage, settle to the actual estimate and release
   unused reserve.
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

Bounded paid wrapper (default cap $0.50, refuses to overwrite):

```sh
python3 -m sasb.pilot --provider anthropic --mode worker --cap-usd 0.50
```

`--force` overwrites an existing `--out`. `--lock` defaults to
`reports/live-run.lock`.

## What this is not

- Not a Stage B measurement.
- Not a swarm experiment unless `--mode swarm` and extra `model_roles`.
- Not a claim that the local estimate matches the bill.
- Not enabled in ordinary CI. The optional paid workflow is manual and starts
  with the offline suite.
