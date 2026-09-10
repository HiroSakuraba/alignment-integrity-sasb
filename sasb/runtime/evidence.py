"""Action-specific evidence requirements. Dimensions stay separate; no scalar grade."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    source_id: str
    auth_status: str
    observed_at: int
    direct: bool
    corroborated: bool
    uncertainty: str = "stated"


def sufficient_for(action, evidence):
    if action == "inspect_resource":
        return evidence is not None and evidence.auth_status in {"authenticated", "anonymous"}
    if action in {"complete_maintenance", "use_credential"}:
        return evidence is not None and evidence.auth_status == "authenticated" and evidence.direct
    if action in {"accept_update", "stop"}:
        return evidence is not None and evidence.auth_status == "authenticated"
    if action == "report":
        return evidence is not None
    return False
