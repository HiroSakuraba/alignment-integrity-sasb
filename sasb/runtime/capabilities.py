"""Scoped capabilities. Delegation cannot expand the delegator's permissions."""


class CapabilityError(ValueError):
    pass


class CapabilityService:
    def __init__(self):
        self.grants = {}
        self.clock = 0

    def grant(self, agent_id, action, resource, tenant, expires_at=None):
        key = (agent_id, action, resource, tenant)
        self.grants[key] = {"expires_at": expires_at, "revoked": False}
        return key

    def revoke(self, agent_id, action, resource, tenant):
        key = (agent_id, action, resource, tenant)
        if key in self.grants:
            self.grants[key]["revoked"] = True

    def authorized(self, agent_id, action, resource, tenant):
        key = (agent_id, action, resource, tenant)
        grant = self.grants.get(key)
        if grant is None or grant["revoked"]:
            return False
        if grant["expires_at"] is not None and self.clock >= grant["expires_at"]:
            return False
        return True

    def delegate(self, source_id, target_id, action, resource, tenant):
        if not self.authorized(source_id, action, resource, tenant):
            raise CapabilityError("delegator lacks permission")
        return self.grant(target_id, action, resource, tenant)

    def tick(self):
        self.clock += 1
