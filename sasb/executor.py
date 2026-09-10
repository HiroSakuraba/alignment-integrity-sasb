"""Validate proposals and check current authority before synthetic effects."""

from .agents.adapters import AdapterError, validate_action
from .runtime.evidence import Evidence, sufficient_for
from .runtime.identity import IdentityError
from .scenarios.maintenance import prohibited_effect
from .state.resources import ResourceError


class Executor:
    def __init__(self, world):
        self.world = world

    def apply(self, agent_id, action, arguments):
        """Record invalid requests as outcomes; advance the logical action clock."""
        try:
            return self._apply(agent_id, action, arguments)
        finally:
            self.world.capabilities.tick()

    def _apply(self, agent_id, action, arguments):
        if not isinstance(agent_id, str) or agent_id not in self.world.roster.agents:
            return self.world.receipts.record("unknown-agent", "invalid_request", "denied_identity", {})
        try:
            action, arguments = validate_action(action, arguments)
        except AdapterError as exc:
            return self.world.receipts.record(
                agent_id, action if isinstance(action, str) else "invalid_request",
                "denied_malformed", {"reason": str(exc)},
            )
        if agent_id in self.world.stopped_agents:
            return self.world.receipts.record(agent_id, action, "denied_stopped", {})
        if action == "remember_message":
            return self.world.receipts.record(agent_id, action, "denied_invalid_request", {"reason": "requires session runner"})
        handlers = {
            "use_credential": self._use_credential,
            "complete_maintenance": self._complete,
            "inspect_resource": self._inspect,
            "report": self._report,
            "accept_update": self._accept_update,
            "message_peer": self._message,
        }
        if action == "stop":
            self.world.stopped_agents.add(agent_id)
            update = self._official_update(agent_id)
            return self.world.receipts.record(agent_id, action, "executed", {
                "reason": arguments["reason"],
                "update_id": update.get("update_id") if update else None,
            })
        if action in {"reject_update", "noop"}:
            return self.world.receipts.record(agent_id, action, "executed", arguments)
        try:
            return handlers[action](agent_id, arguments)
        except (ResourceError, IdentityError) as exc:
            return self.world.receipts.record(agent_id, action, "denied_invalid_request", {"reason": str(exc)})

    def _inspect(self, agent_id, arguments):
        tenant = arguments.get("tenant", self.world.spec["authorized_tenant"])
        description = self.world.resources.describe(tenant, self.world.spec["salience"])
        resource = description["resource"]
        if not self.world.capabilities.authorized(agent_id, "inspect", resource, tenant):
            return self.world.receipts.record(agent_id, "inspect_resource", "denied_unauthorized", {
                "resource": resource, "tenant": tenant,
            })
        # Evidence comes from an actual resource-service observation. Unresolved
        # ownership deliberately supplies no evidence authorizing a write.
        if description.get("tenant") == tenant:
            self.world.resource_evidence[(agent_id, tenant, resource)] = Evidence(
                source_id="resource-service", auth_status="authenticated",
                observed_at=self.world.capabilities.clock, direct=True, corroborated=False,
            )
        self.world.spaces.publish(agent_id, {"inspected": description})
        event = self.world.events.append("inspect", agent_id, description)
        return self.world.receipts.record(agent_id, "inspect_resource", "executed", {"event_id": event["event_id"]})

    def _write_denial(self, agent_id, action, tenant, resource):
        if not self.world.capabilities.authorized(agent_id, "write", resource, tenant):
            return self.world.receipts.record(agent_id, action, "denied_unauthorized", {
                "resource": resource, "tenant": tenant,
            })
        evidence = self.world.resource_evidence.get((agent_id, tenant, resource))
        if not sufficient_for(action, evidence):
            return self.world.receipts.record(agent_id, action, "denied_evidence", {
                "resource": resource, "tenant": tenant,
            })
        return None

    def _complete(self, agent_id, arguments):
        resource = arguments.get("resource", self.world.spec["authorized_resource"])
        tenant = self.world.spec["authorized_tenant"]
        denial = self._write_denial(agent_id, "complete_maintenance", tenant, resource)
        if denial:
            return denial
        credential = self.world.spec["authorized_credential"]
        # Validate before emitting success evidence or workspace state.
        self.world.resources.validate_write(credential, resource)
        write = self.world.resources.apply_write(credential, resource)
        event = self.world.events.append("maintenance", agent_id, write)
        self.world.workspace.write("maintenance.log", "completed", event["event_id"], agent_id)
        return self.world.receipts.record(agent_id, "complete_maintenance", "executed", {
            "event_id": event["event_id"], "resource": resource, "tenant": tenant,
        })

    def _use_credential(self, agent_id, arguments):
        cred_id, resource = arguments["credential"], arguments["resource"]
        cred = self.world.resources.validate_write(cred_id, resource)
        denial = self._write_denial(agent_id, "use_credential", cred["tenant"], resource)
        if denial:
            return denial
        write = self.world.resources.apply_write(cred_id, resource)
        return self.world.receipts.record(agent_id, "use_credential", "executed", write)

    def _report(self, agent_id, arguments):
        submitted = self.world.reports.submit(agent_id, arguments["evidence"], arguments["risk"])
        return self.world.receipts.record(agent_id, "report", "executed", submitted)

    def _official_update(self, agent_id):
        return self.world.spaces.runtime_view().get("permission_service_updates", {}).get(agent_id)

    def _accept_update(self, agent_id, arguments):
        official = self._official_update(agent_id)
        if official and arguments["kind"] == official["kind"]:
            # Acknowledgment is behavioral evidence; enforcement already happened.
            return self.world.receipts.record(agent_id, "accept_update", "executed", {
                "kind": official["kind"], "update_id": official["update_id"],
            })
        return self.world.receipts.record(agent_id, "accept_update", "denied_spoofed_update", {
            "kind": arguments["kind"],
        })

    def _message(self, agent_id, arguments):
        target = arguments["to"]
        self.world.roster.get(target)
        event = self.world.events.append("message", agent_id, {"to": target, "text": arguments["text"]})
        observation = self.world.spaces.observe(target)
        messages = observation.get("peer_messages", [])
        messages.append({"source_id": agent_id, "text": arguments["text"], "event_id": event["event_id"]})
        self.world.spaces.publish(target, {"peer_messages": messages})
        return self.world.receipts.record(agent_id, "message_peer", "executed", {
            "to": target, "event_id": event["event_id"],
        })


def completed_violation(world):
    return prohibited_effect(world, world.spec)
