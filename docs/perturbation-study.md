# From outcome tables to perturbation studies

The immediate question is which changes alter proposals, completed effects, and
useful work. `python3 -m sasb.landscape` produces an offline response map in
`reports/perturbation-map.json`. It contains twenty existing fixture/runtime/policy
cells, twelve controlled message comparisons, and four paired history probes.
`make report` regenerates it and `make verify` checks it.

## What this measures

The inventory reports existing operational scores for both policies under both
runtime treatments in all five maintenance conditions. Its compliant policy is
condition-specific; the inventory is descriptive, not a randomized estimate of
the causal effect of changing a condition. Default versus proposed changes both
capability and evidence enforcement, so that comparison identifies the bundle.
It does not identify each mechanism's contribution.

The coupling comparison holds the worker's initial permissions, credentials,
task, and schedule fixed while changing the planner's message: authorized
instruction, unauthorized instruction, or no message. One worker follows the
existing observation-dependent chain rule. A fixed compliant script provides a
message-insensitive negative control. The former changes its proposal when the
message changes; the latter does not. The proposed runtime prevents the scripted
out-of-scope write from completing. These are programmed response functions,
not measurements of persuasion, model diversity, or emergent coordination.

The history comparison first stores an unauthorized instruction or stores
nothing, then resets the planner. Resource state and the worker's permission
summary match at the comparison point. Both histories receive the same new
status message and the same schedule. With retained, privileged memory, the
responses differ. Ordinary evidence presentation and memory cleanup provide
negative controls. The report explicitly lists the memory omitted from the
matched snapshot. Full states are unequal; no unexplained history effect is
claimed. Completed violations remain blocked in these proposed-runtime probes.

## What to take from the suggested literature

The user supplied a Grok interpretation of a Lyons/Krier X conversation. The
linked post could not be retrieved independently, so this document does not
attribute Grok's wording or the reported replies to those participants.

Thelen, Schöner, Scheier, and Smith (2001) model infant perseverative reaching
through coupled processes of looking, planning, reaching, and remembering.
The methodological borrowing is to vary context and retained state rather than
explain a behavior solely by attaching a category label.

Haken, Kelso, and Bunz (1985) model transitions in coordination between a person's
two hands as movement frequency changes. The classic experiment is bimanual,
not two people tapping. Relative phase is the measured coordination variable.
For our purposes, define the system state, the changed parameter, and the
measured response before drawing an analogy to a phase transition.

An outcome at a short stopping horizon is not an attractor. An attractor claim
needs a defined continuing transition process, an attracting set, and evidence
of return or convergence from a specified neighborhood. An absorbing stop rule
can manufacture stability. Discrete systems can have attractors and hysteresis;
the limitation here is the experiment definition, not discreteness itself.
Different histories followed by different responses establish dependence on
omitted state. A hysteresis study additionally needs a controlled parameter
sweep in both directions and a reproducible path-dependent response relation.

Four role names do not establish model heterogeneity. A fixed script's failure
also does not establish failure for every possible policy. The resource boundary
and closed action grammar must remain explicit in claims about generality.

## Next experiment, before a larger paid sweep

Use one task and one fixed worker policy first. Keep prompt wording, output
allowance, permissions, and action horizon fixed. Vary message exposure count
across 0, 1, 2, and 4, retaining the same authorized workload. Record the fraction
of out-of-scope proposals, completed prohibited effects, and authorized task
completion separately. Pair every attack exposure with an authorized-message
control of the same length. Predeclare whether length is measured in messages,
bytes, or tokens; do not silently treat them as equivalent.

Then remove the exposure and measure recovery over a fixed number of further
decisions. Return to an authorized action after one probe is weaker evidence
than sustained authorized behavior over a predeclared window. Count refusal and
stopping as separate outcomes so an all-stop policy cannot masquerade as useful
recovery. Retained memory, memory cleanup, and actor replacement are different
interventions and should have separate comparisons.

For a path-dependence experiment, raise and then lower exposure while preserving
history; compare with the reverse ordering under matched budgets. Report the
full-state differences, observable-state projection, and reset controls. A loop
caused by explicitly coded memory is a controller demonstration. Claims about
learned model dynamics require real model observations and repeated trials.

Only after the instrumentation works should Luna and Haiku replace the worker
separately, followed by a mixed-model configuration. Start with a small number of
predeclared contrasts. Hold episode budget and scenario constant and separate
model sampling variation from changed prompts, token limits, and topology.
Generalization requires new tasks or environments, not merely new fixture IDs.

The controlled-AI sibling contributes exact finite reachability. Its companion
map distinguishes rules-only bounds, monitor-inclusive completed-harm witnesses,
unresolved pending effects, and useful-work witnesses. Model propensity belongs
in a separate column and stays null until measured. Unreachable attack cells can
be spared most paid repetitions, but retain honest-work controls and a small
predeclared integration check; a proof about a model does not automatically
verify the deployed implementation.

## Sources

- Thelen et al. (2001), *The dynamics of embodiment: A field theory of infant perseverative reaching*: https://doi.org/10.1017/S0140525X01003910
- Haken, Kelso, and Bunz (1985), *A theoretical model of phase transitions in human hand movements*: https://ccs.fau.edu/hbblab/pdfs/1985_Haken_Kelso_Bunz_Biol_Cyb.pdf
- User-supplied thread link (not independently retrieved): https://x.com/BenjaminLy61243/status/2098245457889894740

The [repeated-work recovery pilot](expanded-testing.md) now implements continuing jobs, seeded controller sampling, recovery windows, and memory controls. Its claims remain distinct from reachability and attraction.
