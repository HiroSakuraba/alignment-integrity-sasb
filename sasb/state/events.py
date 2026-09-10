"""Durable event records separate from revisable risk assessments."""

import itertools
import time


class EventLog:
    def __init__(self):
        self._ids = itertools.count(1)
        self.events = []

    def append(self, kind, source_id, payload, parent_id=None, verified_ancestry=None):
        event = {
            "event_id": next(self._ids),
            "kind": kind,
            "source_id": source_id,
            "payload": payload,
            "parent_event_id": parent_id,
            "source_event_ids": list(verified_ancestry or []),
            "claimed_ancestry": payload.get("claimed_ancestry", []) if isinstance(payload, dict) else [],
            "observed_at": time.time(),
        }
        self.events.append(event)
        return event

    def by_id(self, event_id):
        for event in self.events:
            if event["event_id"] == event_id:
                return event
        raise KeyError(event_id)
