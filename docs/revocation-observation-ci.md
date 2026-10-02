# Offline CI guarantees

The dedicated workflow sets both live-call interlocks to disabled values and invokes only unit tests plus `python -m sasb.revocation_observation`.

It does not invoke `sasb.live`, does not load provider credentials, and does not select OpenAI or Anthropic providers. The probe itself imports only the deterministic world, executor, observation, and scenario modules.
