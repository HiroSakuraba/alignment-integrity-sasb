"""Named runtime treatments for the Stage B A-versus-B comparison.

Both treatments keep the outer sandbox: no network, no real credentials, and
no writes outside the synthetic resource service and workspace. They differ
only in the simulated controls being evaluated.
"""

PROPOSED = "proposed"
DEFAULT = "default"
TREATMENTS = frozenset({PROPOSED, DEFAULT})


class TreatmentError(ValueError):
    pass


def validate_runtime(runtime):
    if runtime not in TREATMENTS:
        raise TreatmentError("unknown runtime treatment: " + repr(runtime))
    return runtime
