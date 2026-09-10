# Contributing

This repository makes narrow claims about a scripted Stage A harness. Keep an implementation claim separate from a claim about learned models or deployed systems.

Before opening a change:

1. Run the test suite and report verifier.
2. Add a regression test for every fixed isolation or scoring defect.
3. Update `reports/harness-run.json` if deterministic results change.
4. State whether the change alters the threat model, protocol, or scenario family.
5. Do not add API keys, credentials, or live provider clients.

Treat malformed model output, timeout, and retry behavior as measured outcomes once providers exist. Do not silently drop failed episodes.
