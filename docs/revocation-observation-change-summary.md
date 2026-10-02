# Change summary

This branch preserves prior SASB experiments and reports. It changes only the observation path needed for the proposed follow-up:

1. records successful update acknowledgments as interface state;
2. supports persistent, acknowledged, and consumed post-ack update representations;
3. removes `runtime_treatment` from the worker-visible capability summary;
4. adds deterministic no-network probes and regression tests.

The default observation mode remains `persistent`, so prior update visibility is retained unless the new mode is explicitly selected.
