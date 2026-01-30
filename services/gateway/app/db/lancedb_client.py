from __future__ import annotations


class LanceDBClient:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db = None

    def connect(self):
        import lancedb

        if self._db is None:
            self._db = lancedb.connect(self.path)
        return self._db
