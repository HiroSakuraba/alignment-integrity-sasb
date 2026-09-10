"""Persistent coding workspace with provenance on every write."""


class Workspace:
    def __init__(self):
        self.files = {}
        self.history = []

    def write(self, path, content, source_event_id, agent_id):
        record = {
            "path": path,
            "content": content,
            "source_event_id": source_event_id,
            "agent_id": agent_id,
        }
        self.files[path] = record
        self.history.append(record)
        return record

    def read(self, path):
        return self.files.get(path)
