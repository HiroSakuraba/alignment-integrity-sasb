"""Provider boundary. Network calls stay off until two explicit local switches exist.

No keys are stored here. A live model run also needs a recorded wire-format
validation, as in controlled-ai-research/docs/model-experiment-protocol.md.
"""

import os


class ProviderDisabled(RuntimeError):
    pass


def live_calls_allowed():
    return os.environ.get("SASB_ENABLE_NETWORK") == "1" and os.environ.get("SASB_PROVIDER_VALIDATED") == "1"


def require_live():
    if not live_calls_allowed():
        raise ProviderDisabled("model providers are disabled; set SASB_ENABLE_NETWORK=1 and SASB_PROVIDER_VALIDATED=1 only after protocol checks")
