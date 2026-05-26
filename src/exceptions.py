class AppError(Exception):
    default_message = "Application error"

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class UnauthorizedError(AppError):
    default_message = "Unauthorized"


class InvalidCredentialsError(UnauthorizedError):
    default_message = "Invalid username or password"


class InvalidTokenError(UnauthorizedError):
    default_message = "Invalid token"


class AuthenticationRequiredError(UnauthorizedError):
    default_message = "Authentication required"


class AuthenticatedUserNotFoundError(UnauthorizedError):
    default_message = "Authenticated user not found"


class NotFoundError(AppError):
    default_message = "Entity not found"


class ConflictError(AppError):
    default_message = "Conflict"


class ForbiddenError(AppError):
    default_message = "Forbidden"


class UserNotFoundError(NotFoundError):
    default_message = "User not found"


class EmailAlreadyExistsError(ConflictError):
    default_message = "User with this email already exists"


class UsernameAlreadyExistsError(ConflictError):
    default_message = "User with this username already exists"


class NotificationNotFoundError(NotFoundError):
    default_message = "Notification not found"


class NotificationAccessDeniedError(ForbiddenError):
    default_message = "Not authorized to access this notification"


class RateLimitExceededError(AppError):
    default_message = "Rate limit exceeded"

    def __init__(self, retry_after: int, message: str | None = None):
        self.retry_after = retry_after
        super().__init__(
            message or f"Rate limit exceeded. Try again in {retry_after} seconds."
        )
