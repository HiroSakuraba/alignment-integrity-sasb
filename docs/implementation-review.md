# Implementation review and priorities

The project has a useful architectural separation between actor observations, trusted execution, and evaluator state. Its strongest present contribution is a small, reproducible fixture for checking those boundaries. Scientific conclusions require a substantially richer experimental setup.

## Integrated improvements

- Recursively validate JSON-shaped observations and copy values at publication and read boundaries.
- Preserve delegation lineage so expiry, revocation, and parent replacement invalidate descendants.
- Enforce revocation before notification; treat acknowledgment as behavior and make stop terminal.
- Require resource-service inspection evidence instead of inventing evidence at write time.
- Validate proposals and credential bindings before effects; retain adapter failures and raised timeouts as outcomes.
- Preserve peer-message history and stamp senders in the runtime.
- Score independent effects, task artifacts, report delivery, correction, refusal, and escalation separately, with explicit applicable counts.
- Exercise the outcome checker with permitted and prohibited bypass controls.

Regression tests cover these properties. Passing them validates the implementation against these fixtures; it does not establish model alignment, attack coverage, or a training benefit.

## Recommended next work

| Priority | Improvement | Concrete completion criterion |
| --- | --- | --- |
| 1 | Extend the implemented local session runner | Round-robin decisions, action budgets, local per-call timeouts, full traces, attributed memory, and resets now have deterministic controls. Next add cumulative token/cost accounting and an isolated provider-neutral worker boundary before connecting models. |
| 2 | Expand independent task and outcome validation | Add a real synthetic workspace task with attacker-controlled content, a hidden task checker, benign twins, and tampering/recovery cases. Record ordered effects and revocations so the evaluator can distinguish writes before and after a mid-episode authority change. |
| 3 | Define the controlled runtime comparison | Scripted `default` vs `proposed` treatments now exist. The default path can complete a prohibited synthetic write; the proposed path converts that into an unauthorized attempt. Next attach a model only after a provider client exists. |
| 4 | Prepare a reproducible baseline pilot | Blocked on API access. Identity records and prompt hashes are in place. Do not enable network flags without a validated client. |

The current ownership-salience pair can check that runtime rules do not depend on a person's name. Scripted actors cannot establish that social salience changes model behavior. Likewise, the tempting-credential fixture does not establish emergent collusion, subliminal transfer, or durable persona change.

Permit integration should follow a concrete threat requirement and its tests. Adding a signer without routing every relevant effect through permit verification would provide no additional enforcement. Training experiments should follow a validated baseline and evaluator, as specified in the research framework.
