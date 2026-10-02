# Implementation boundaries

The branch intentionally does **not** change the capability revocation mechanism, the default/proposed runtime definitions, the existing Stage B live driver, provider model pins, or prior reports.

New mutable state is limited to `World.acknowledged_updates`, which records that an update event has been handled. This state is behavioral/interface state only. `CapabilityService` remains the source of execution authority.

`runtime_treatment` remains in trusted runtime/evaluator records for analysis, but is no longer copied into `capability_summary` shown to the agent.

The three observation modes are configured when a `World` is constructed. The default is `persistent`, preserving prior observation behavior except for removal of the leaked treatment label.
