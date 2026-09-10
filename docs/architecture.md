# Architecture

```mermaid
flowchart TD
  Planner["Planner"] --> Runner["Episode runner"]
  Worker["Worker"] --> Runner
  Reviewer["Reviewer"] --> Runner
  Coordinator["Coordinator"] --> Runner
  Runner --> Spaces["Information spaces"]
  Spaces --> Obs["Agent observations"]
  Spaces --> Runtime["Trusted runtime"]
  Spaces --> Eval["Evaluator-only state"]
  Runner --> Executor["Executor"]
  Caps["Capability service"] --> Executor
  Executor --> Resources["Synthetic resource service"]
  Executor --> Workspace["Provenance workspace"]
  Executor --> Reports["Authenticated report channel"]
  Executor --> Receipts["Action receipts"]
```

Scripted actors return structured decisions. The JSON adapter validates action names, required arguments, types, duplicate keys, and unexpected fields. The executor checks each proposal and records its result; the current report does not retain raw actor output or usage. Adapter errors and raised timeouts produce receipts and terminate that actor. There is no active wall-clock timeout mechanism yet.

Consequential writes require a current capability for the agent, tenant, resource, and action, plus direct authenticated evidence from a successful inspection. Evidence is episode-local; freshness thresholds and changing resource ownership are not modeled. Each attempted action advances the logical capability clock. Delegation follows the complete grant lineage, including expiry and revocation. Regranting a parent does not revive its old descendants.

The trusted controller revokes permission before publishing an update. Actor acknowledgment never authorizes the change. Stop is terminal for the actor. Peer messages retain their history and runtime-assigned sender identity but confer no authority.

Observation publication rejects forbidden keys recursively in dictionaries and lists and returns defensive copies. This is an in-process data contract, not semantic information-flow verification or process isolation.

The workspace stores a maintenance completion marker with event provenance. It is not an independent coding or document-editing environment. The HMAC permit helper is standalone and is not on the executor path.

This diagram is an interface map, not a deployment claim. Trust assumptions are in the [threat model](threat-model.md).
