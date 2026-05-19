from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitExceededError,
    UnauthorizedError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        status_code = 500

        if isinstance(exc, UnauthorizedError):
            status_code = 401
        elif isinstance(exc, NotFoundError):
            status_code = 404
        elif isinstance(exc, ConflictError):
            status_code = 409
        elif isinstance(exc, ForbiddenError):
            status_code = 403
        elif isinstance(exc, RateLimitExceededError):
            status_code = 429

        headers = {}
        if isinstance(exc, RateLimitExceededError):
            headers["Retry-After"] = str(exc.retry_after)

        return JSONResponse(
            status_code=status_code,
            content={"detail": str(exc)},
            headers=headers,
        )
