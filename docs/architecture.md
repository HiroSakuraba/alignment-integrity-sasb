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

Actors emit JSON decisions. The runner records every decision before the executor applies it. Consequential writes require a current capability grant for that agent, tenant, resource, and action. Evaluator labels never enter observations.

This diagram is an interface map, not a deployment claim. Trust assumptions are in the [threat model](threat-model.md).
