# Contributing

This repository makes narrow claims about a scripted Stage A harness. Keep an implementation claim separate from a claim about learned models or deployed systems.

Before opening a change:

1. Run the test suite and report verifier.
2. Add a regression test for every fixed isolation or scoring defect.
3. Update `reports/harness-run.json` if deterministic results change.
4. State whether the change alters the threat model, protocol, or scenario family.
5. Do not commit API keys or credentials. Live provider work must remain disabled by default, use the shared request budget, and have offline regression tests. Do not start paid runs without operator authorization.

Treat malformed model output, timeout, and retry behavior as measured outcomes once providers exist. Do not silently drop failed episodes.
