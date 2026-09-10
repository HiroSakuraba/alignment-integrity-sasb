"""Authenticated report tool outside ordinary peer routing."""

import uuid


class ReportChannel:
    def __init__(self, owner="coordinator"):
        self.owner = owner
        self.reports = []

    def submit(self, agent_id, evidence, risk):
        report = {
            "report_id": uuid.uuid4().hex,
            "agent_id": agent_id,
            "evidence": evidence,
            "risk": risk,
            "owner": self.owner,
            "acknowledged": True,
        }
        self.reports.append(report)
        return {"receipt": report["report_id"], "owner": self.owner}

    def delivered(self):
        return list(self.reports)
