"""Scoped capabilities. Delegation cannot expand the delegator's permissions."""


class CapabilityError(ValueError):
    pass


class CapabilityService:
    def __init__(self):
        self.grants = {}
        self.clock = 0

    def grant(self, agent_id, action, resource, tenant, expires_at=None):
        key = (agent_id, action, resource, tenant)
        # Replacing a grant must not resurrect descendants of its old generation.
        if key in self.grants:
            self.grants[key]["revoked"] = True
        self.grants[key] = {"key": key, "expires_at": expires_at, "revoked": False, "parent": None}
        return key

    def revoke(self, agent_id, action, resource, tenant):
        key = (agent_id, action, resource, tenant)
        if key in self.grants:
            self.grants[key]["revoked"] = True

    def authorized(self, agent_id, action, resource, tenant):
        key = (agent_id, action, resource, tenant)
        grant = self.grants.get(key)
        if grant is None:
            return False
        seen = set()
        while grant is not None:
            if id(grant) in seen or grant["revoked"]:
                return False
            seen.add(id(grant))
            if grant["expires_at"] is not None and self.clock >= grant["expires_at"]:
                return False
            grant = grant["parent"]
        return True

    def delegate(self, source_id, target_id, action, resource, tenant):
        if not self.authorized(source_id, action, resource, tenant):
            raise CapabilityError("delegator lacks permission")
        parent = self.grants[(source_id, action, resource, tenant)]
        target_key = (target_id, action, resource, tenant)
        ancestor = parent
        while ancestor is not None:
            if ancestor["key"] == target_key:
                raise CapabilityError("cyclic delegation")
            ancestor = ancestor["parent"]
        key = self.grant(target_id, action, resource, tenant, parent["expires_at"])
        self.grants[key]["parent"] = parent
        return key

    def tick(self):
        self.clock += 1
