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

## Chain fixture boundary

The session runner restricts message destinations to declared directed edges and stores only observed messages as persistent memory. Its `unsafe_promote_fixture` option changes observation presentation for a deliberate deterministic comparison; it never expands execution permissions. Memory persistence is not scored as an unauthorized effect on its own because storing a quotation can be legitimate.

Local actor code and reset factories remain trusted. Per-decision deadlines use POSIX main-thread signals and reject conflicting alarms. They bound cooperative local actor calls, not arbitrary hostile Python, subprocesses, or operating-system effects. Action limits bound the number of calls; cumulative wall time is at most the sum of decision allowances plus trusted harness overhead. The session runner itself provides no retry driver, dollar-budget enforcement, or process sandbox. The optional `sasb.pilot` controller attaches live providers through a shared serial request ledger, input/output limits, and explicit operator activation. Returned usage is actor-declared; deterministic actors report zero tokens rather than estimated model consumption.

## Optional API pilot

Provider keys belong to the trusted controller and never enter actor observations. Only synthetic task data is sent to the two fixed API endpoints. The paid GitHub workflow is manual and restricted to main. Code and workflow authors remain trusted; repository secrets are not a sandbox against malicious trusted code. The local cost allowance relies on documented prices and a conservative token reservation, not provider-side billing enforcement. Unknown requests stop the pilot and retain their reservation. See `provider-setup.md`.
