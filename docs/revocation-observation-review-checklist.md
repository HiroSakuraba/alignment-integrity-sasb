# Pre-merge review checklist

- [ ] Full existing unit suite passes.
- [ ] Focused revocation observation tests pass.
- [ ] Zero-cost probe reports `network: false`.
- [ ] No provider credentials are required by offline workflow.
- [ ] `runtime_treatment` is absent from agent-visible observations.
- [ ] Runtime treatment remains available in evaluator records.
- [ ] Revocation is effective before notification in all modes.
- [ ] Acknowledgment never restores write authority.
- [ ] Persistent/acknowledged/consumed are identical before acknowledgment.
- [ ] Existing live experiment driver and previous reports are preserved.
- [ ] No merge to `main` until explicit review.
