import json
from typing import Optional
from redis.asyncio import Redis
from app.core.config import settings

class ContentCache:
    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def key(content_hash: str) -> str:
        return f"content-result:{content_hash}"

    async def get(self, content_hash: str) -> Optional[dict]:
        raw = await self.redis.get(self.key(content_hash))
        return json.loads(raw) if raw else None

    async def set(self, content_hash: str, result: dict):
        await self.redis.set(
            self.key(content_hash),
            json.dumps(result, default=str),
            ex=settings.cache_ttl_seconds,
        )
