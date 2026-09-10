"""Externally recorded execution results, including denials."""

import json
import time
import uuid


class ReceiptLog:
    def __init__(self):
        self.items = []

    def record(self, agent_id, action, decision, details=None):
        item = {
            "receipt_id": uuid.uuid4().hex,
            "agent_id": agent_id,
            "action": action,
            "decision": decision,
            "details": details or {},
            "recorded_at": time.time(),
        }
        self.items.append(item)
        return item

    def decisions(self):
        return [item["decision"] for item in self.items]

    def dump(self):
        return json.loads(json.dumps(self.items, default=str))
