# Frozen offline scope

The current branch is limited to validating the observation manipulation and removing evaluator-treatment leakage. It does not run Luna, Haiku, or any other external model.

The offline test does not claim anything about model behavior. It checks that the future paid experiment would manipulate only the post-acknowledgment representation while preserving the same revoked authority state.
