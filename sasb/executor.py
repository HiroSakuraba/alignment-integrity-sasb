"""Models propose actions; the runtime checks identity, scope, and evidence."""

from .runtime.evidence import Evidence, sufficient_for
from .scenarios.maintenance import prohibited_effect


class Executor:
    def __init__(self, world):
        self.world = world

    def apply(self, agent_id, action, arguments):
        spec = self.world.spec
        agent = self.world.roster.get(agent_id)
        evidence = Evidence(
            source_id=agent_id,
            auth_status="authenticated",
            observed_at=self.world.capabilities.clock,
            direct=True,
            corroborated=False,
        )
        if action == "use_credential":
            return self._use_credential(agent_id, arguments, evidence)
        if action == "complete_maintenance":
            return self._complete(agent_id, arguments, evidence)
        if action == "inspect_resource":
            return self._inspect(agent_id, arguments)
        if action == "report":
            return self._report(agent_id, arguments, evidence)
        if action == "accept_update":
            return self._accept_update(agent_id, arguments, evidence)
        if action == "reject_update":
            receipt = self.world.receipts.record(agent_id, action, "executed", {"reason": arguments.get("reason")})
            return receipt
        if action == "stop":
            receipt = self.world.receipts.record(agent_id, action, "executed", {"reason": arguments.get("reason")})
            return receipt
        if action == "message_peer":
            target = arguments.get("to")
            text = arguments.get("text", "")
            if target:
                self.world.spaces.publish(target, {"peer_message": text, "peer_from": agent["role"]})
            receipt = self.world.receipts.record(agent_id, action, "executed", {"to": target})
            return receipt
        if action == "noop":
            return self.world.receipts.record(agent_id, action, "executed", {})
        return self.world.receipts.record(agent_id, action, "denied_unknown", {})

    def _inspect(self, agent_id, arguments):
        tenant = arguments.get("tenant") or self.world.spec["authorized_tenant"]
        description = self.world.resources.describe(tenant, self.world.spec["salience"])
        self.world.spaces.publish(agent_id, {"inspected": description})
        event = self.world.events.append("inspect", agent_id, description)
        return self.world.receipts.record(agent_id, "inspect_resource", "executed", {"event_id": event["event_id"]})

    def _complete(self, agent_id, arguments, evidence):
        resource = arguments.get("resource", self.world.spec["authorized_resource"])
        tenant = self.world.spec["authorized_tenant"]
        if not sufficient_for("complete_maintenance", evidence):
            return self.world.receipts.record(agent_id, "complete_maintenance", "denied_evidence", {})
        if not self.world.capabilities.authorized(agent_id, "write", resource, tenant):
            return self.world.receipts.record(agent_id, "complete_maintenance", "denied_unauthorized", {
                "resource": resource, "tenant": tenant,
            })
        event = self.world.events.append("maintenance", agent_id, {"resource": resource, "tenant": tenant})
        self.world.workspace.write("maintenance.log", "completed", event["event_id"], agent_id)
        self.world.resources.apply_write("cred_a", resource)
        return self.world.receipts.record(agent_id, "complete_maintenance", "executed", {"event_id": event["event_id"]})

    def _use_credential(self, agent_id, arguments, evidence):
        cred_id = arguments.get("credential")
        resource = arguments.get("resource")
        cred = self.world.resources.credential(cred_id)
        if not self.world.capabilities.authorized(agent_id, cred["action"], cred["resource"], cred["tenant"]):
            return self.world.receipts.record(agent_id, "use_credential", "denied_unauthorized", {
                "credential": cred_id, "resource": resource, "tenant": cred["tenant"],
            })
        if not sufficient_for("use_credential", evidence):
            return self.world.receipts.record(agent_id, "use_credential", "denied_evidence", {})
        write = self.world.resources.apply_write(cred_id, resource)
        return self.world.receipts.record(agent_id, "use_credential", "executed", write)

    def _report(self, agent_id, arguments, evidence):
        if not sufficient_for("report", evidence):
            return self.world.receipts.record(agent_id, "report", "denied_evidence", {})
        submitted = self.world.reports.submit(agent_id, arguments.get("evidence"), arguments.get("risk"))
        return self.world.receipts.record(agent_id, "report", "executed", submitted)

    def _accept_update(self, agent_id, arguments, evidence):
        observation = self.world.spaces.observe(agent_id)
        official = observation.get("permission_service_update")
        kind = arguments.get("kind")
        if official and official.get("auth_status") == "authenticated" and official.get("source") == "permission-service":
            if official.get("kind") == "revoke":
                self.world.capabilities.revoke(
                    agent_id, "write", official["resource"], official["tenant"],
                )
            return self.world.receipts.record(agent_id, "accept_update", "executed", {"kind": kind})
        return self.world.receipts.record(agent_id, "accept_update", "denied_spoofed_update", {"kind": kind})


def completed_violation(world):
    return prohibited_effect(world, world.spec)
