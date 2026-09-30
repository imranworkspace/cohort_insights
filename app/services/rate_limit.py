from redis.asyncio import Redis
from app.core.config import settings

ACTIVE_KEY = "active-documents:{}"

RESERVE_SCRIPT = '''
local key = KEYS[1]
local current = tonumber(redis.call("GET", key) or "0")
if current >= 3 then
    return 0
end
redis.call("INCR", key)
redis.call("EXPIRE", key, ARGV[1])
return 1
'''

RELEASE_SCRIPT = '''
local key = KEYS[1]
local current = tonumber(redis.call("GET", key) or "0")
if current <= 1 then
    redis.call("DEL", key)
else
    redis.call("DECR", key)
    redis.call("EXPIRE", key, ARGV[1])
end
return 1
'''

class ActiveJobLimiter:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def reserve(self, user_id: str) -> bool:
        result = await self.redis.eval(
            RESERVE_SCRIPT, 1, ACTIVE_KEY.format(user_id),
            settings.active_job_ttl_seconds
        )
        return bool(result)

    async def release(self, user_id: str):
        await self.redis.eval(
            RELEASE_SCRIPT, 1, ACTIVE_KEY.format(user_id),
            settings.active_job_ttl_seconds
        )
