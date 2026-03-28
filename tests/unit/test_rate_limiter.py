from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.exceptions import RateLimitExceededError
from src.services.rate_limiter import RateLimiter


class TestRateLimiter:
    """Проверяю внешний контракт rate limiter без реального Redis."""

    async def test_allows_request_when_limit_is_not_exceeded(self):
        """Если Redis разрешил запрос, limiter не должен бросать исключение."""
        redis = MagicMock()
        redis.eval = AsyncMock(return_value=[1, 4])

        limiter = RateLimiter(redis, max_requests=5, window_seconds=60)
        limiter._now_ms = MagicMock(return_value=1000)
        limiter._build_member = MagicMock(return_value="1000:test")

        user_id = uuid4()
        await limiter.check_limit(user_id)

        redis.eval.assert_awaited_once()
        args = redis.eval.await_args.args
        assert args[1] == 1
        assert args[2] == f"rate_limit:{user_id}"
        assert args[3] == 1000
        assert args[4] == 60000
        assert args[5] == 5
        assert args[6] == "1000:test"

    async def test_raises_429_when_limit_is_exceeded(self):
        """Если слот закончился, limiter должен превратить это в понятный 429."""
        redis = MagicMock()
        redis.eval = AsyncMock(return_value=[0, 1500])

        limiter = RateLimiter(redis, max_requests=5, window_seconds=60)
        limiter._now_ms = MagicMock(return_value=1000)
        limiter._build_member = MagicMock(return_value="1000:test")

        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.check_limit(uuid4())

        assert exc_info.value.retry_after == 2
        assert str(exc_info.value) == "Rate limit exceeded. Try again in 2 seconds."


    def test_rejects_invalid_configuration(self):
        """Плохую конфигурацию лучше поймать сразу при создании объекта."""
        redis = MagicMock()

        with pytest.raises(ValueError):
            RateLimiter(redis, max_requests=0, window_seconds=60)

        with pytest.raises(ValueError):
            RateLimiter(redis, max_requests=5, window_seconds=0)
