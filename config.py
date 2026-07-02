"""
config.py — JSON database (thread-safe).
"""

import json
import os
import threading

DB_PATH = "data/db.json"
DEFAULT_PREFIX = ","


class Database:
    def __init__(self):
        self._lock = threading.Lock()
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(DB_PATH):
            with open(DB_PATH, "w") as f:
                json.dump({}, f)

    def _read(self) -> dict:
        with open(DB_PATH, "r") as f:
            return json.load(f)

    def _write(self, data: dict):
        with open(DB_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def get(self, key: str, default=None):
        with self._lock:
            data = self._read()
            return data.get(key, default)

    def get_guild(self, guild_id: int) -> dict:
        with self._lock:
            data = self._read()
            return data.get("guilds", {}).get(str(guild_id), {})

    def update_guild(self, guild_id: int, config: dict):
        with self._lock:
            data = self._read()
            data.setdefault("guilds", {})[str(guild_id)] = config
            self._write(data)


db = Database()
