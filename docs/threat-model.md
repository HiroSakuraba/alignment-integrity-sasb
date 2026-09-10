# Prototype threat model

Stage A assumes that the Python process, capability table, evaluator dictionary, and HMAC permit key are not controlled by any acting model. It does not claim protection if an attacker can edit this source, publish evaluator fields into observations by changing the code, or call `ResourceService.apply_write` directly.

The outer sandbox is the operator's machine. The synthetic resource service never contacts a real tenant. Credentials `cred_a` and `cred_b` are fixture identifiers.

## Separation

Three spaces are enforced in process:

- Agent observations: task text, ownership facts, tool responses, peer messages.
- Trusted runtime: identities, grants, revocations, policy id.
- Evaluator-only: attack status, hidden outcomes, grader reliability, expected behavior.

A production deployment needs separate credentials for the evaluator and the permission service. The local HMAC permit store is a rehearsal copied from `controlled-ai-research`; replace it with an external signer before any non-fixture effect.

## What this does not cover

Compromise of the controller or verifier, learned behavioral change, subliminal transfer through synthetic data, and long-horizon zero-seed strategy generation. Those are later stages in the framework, not properties of this harness.
