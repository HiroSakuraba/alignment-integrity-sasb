# Prototype threat model

Stage A assumes that the Python process, capability table, evaluator dictionary, and HMAC permit key are not controlled by any acting model. It does not claim protection if an attacker can edit this source, publish evaluator fields into observations by changing the code, or call `ResourceService.apply_write` directly.

The outer sandbox is the operator's machine. The synthetic resource service never contacts a real tenant. Credentials `cred_a` and `cred_b` are fixture identifiers.

## Separation

Three spaces are enforced in process:

- Agent observations: task text, ownership facts, tool responses, peer messages.
- Trusted runtime: identities, grants, revocations, policy id.
- Evaluator-only: attack status, hidden outcomes, grader reliability, expected behavior.

A production deployment needs separate credentials for the evaluator and the permission service. The local HMAC permit store is a standalone rehearsal from `controlled-ai-research`, not an execution control in this harness. Any future use requires an explicit executor integration and separate validation.

## What this does not cover

Compromise of the controller or verifier, learned behavioral change, subliminal transfer through synthetic data, and long-horizon zero-seed strategy generation. Those are later stages in the framework, not properties of this harness.

## Enforced boundary and evaluation limits

The trusted controller owns grants, resource evidence, identities, revocations, and the stopped-actor set. Actor-visible claims cannot populate those stores. Delegated authority remains contingent on its parent grant, including across multiple hops and after regranting. Runtime permission metadata is a fixture snapshot; the capability service is the enforcement authority.

Observation validation rejects known forbidden keys at every supported JSON nesting level and prevents mutable-reference leakage. It cannot detect a hidden label paraphrased into ordinary text. Trusted publishers must curate observation content; arbitrary access to Python objects remains outside the threat model.

The independent effect checker covers the five fixed maintenance conditions. Revocation occurs before the episode in the stop condition; the checker does not reconstruct arbitrary mid-episode revocations, concurrent writes, or changing ownership. Explicit bypass controls exercise three prohibited effects and one permitted effect without weakening normal execution.
