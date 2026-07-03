"""
config.py — MongoDB database (persistent across deploys).
"""

import os
from pymongo import MongoClient

DEFAULT_PREFIX = ","

_client = MongoClient(os.getenv("MONGO_URI"))
_db = _client["bot"]
_guilds = _db["guilds"]


class Database:
    def get_guild(self, guild_id: int) -> dict:
        doc = _guilds.find_one({"_id": str(guild_id)})
        if doc:
            doc.pop("_id", None)
        return doc or {}

    def update_guild(self, guild_id: int, config: dict):
        config.pop("_id", None)
        _guilds.replace_one({"_id": str(guild_id)}, {"_id": str(guild_id), **config}, upsert=True)

    def get(self, key: str, default=None):
        doc = _db["meta"].find_one({"_id": key})
        return doc.get("value", default) if doc else default


db = Database()
