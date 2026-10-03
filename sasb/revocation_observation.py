"""Zero-cost scripted probe for revocation observation semantics.

This module never constructs a provider client and never makes network calls.
It checks every revocation observation mode against the same authoritative
revoked state.
"""

import json

from .executor import Executor
from .observations import enrich_observation
from .scenarios.maintenance import specification
from .world import World

from .observations import REVOCATION_OBSERVATION_MODES as MODES


def run_probe():
    rows = []
    for mode in MODES:
        world = World(specification("valid_stop"), revocation_observation_mode=mode)
        before = enrich_observation(world, "worker-1")
        update = before["permission_service_update"]
        ack = Executor(world).apply("worker-1", "accept_update", {"kind": "revoke"})
        repeat_ack = Executor(world).apply("worker-1", "accept_update", {"kind": "revoke"})
        after = enrich_observation(world, "worker-1")
        write = Executor(world).apply("worker-1", "complete_maintenance", {"resource": "test-db"})
        rows.append({
            "mode": mode,
            "network": False,
            "update_id": update["update_id"],
            "ack_decision": ack["decision"],
            "post_ack_update_present": "permission_service_update" in after,
            "post_ack_marked_acknowledged": bool(after.get("permission_service_update", {}).get("acknowledged")),
            "repeat_ack_decision": repeat_ack["decision"],
            "standing_record_present": bool(after.get("revocations_in_effect")),
            "state_key_present": "revocation_in_effect" in after,
            "ack_receipt": [r for r in after["own_receipts"] if r["action"] == "accept_update"][0],
            "task_status_before_ack": (before.get("task_status") or {}).get("state"),
            "current_permissions": after["capability_summary"]["permissions"],
            "runtime_treatment_visible": "runtime_treatment" in after["capability_summary"],
            "revoked_write_decision": write["decision"],
            "writes": list(world.resources.writes),
        })
    return {"experiment": "revocation-observation-semantics-offline-probe-v1", "network": False, "rows": rows}


if __name__ == "__main__":
    print(json.dumps(run_probe(), indent=2, sort_keys=True))
