import math
import time
from uuid import UUID, uuid4

from redis.asyncio import Redis

from src.exceptions import RateLimitExceededError

# language=lua
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call("ZREMRANGEBYSCORE", key, 0, now_ms - window_ms)

local count = redis.call("ZCARD", key)
if count >= limit then
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    if oldest[2] ~= nil then
        local retry_after_ms = window_ms - (now_ms - tonumber(oldest[2]))
        return {0, retry_after_ms}
    end
    return {0, window_ms}
end

redis.call("ZADD", key, now_ms, member)
redis.call("PEXPIRE", key, window_ms)

return {1, limit - count - 1}
"""


class RateLimiter:
    """Redis-backed sliding window rate limiter."""

    def __init__(
        self,
        redis_client: Redis,
        max_requests: int,
        window_seconds: int,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be greater than 0")
        if window_seconds < 1:
            raise ValueError("window_seconds must be greater than 0")

        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.window_ms = window_seconds * 1000

    async def check_limit(self, user_id: UUID) -> None:
        key = self._build_key(user_id)
        now_ms = self._now_ms()
        member = self._build_member(now_ms)

        result = await self.redis.eval(
            RATE_LIMIT_SCRIPT,
            1,
            key,
            now_ms,
            self.window_ms,
            self.max_requests,
            member,
        )

        is_allowed = bool(int(result[0]))
        if is_allowed:
            return

        retry_after_ms = int(result[1])
        retry_after_seconds = max(1, math.ceil(retry_after_ms / 1000))

        raise RateLimitExceededError(retry_after=retry_after_seconds)

    @staticmethod
    def _build_key(user_id: UUID) -> str:
        return f"rate_limit:{user_id}"

    @staticmethod
    def _build_member(now_ms: int) -> str:
        return f"{now_ms}:{uuid4()}"

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
