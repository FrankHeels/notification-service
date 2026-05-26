from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
    UsernameAlreadyExistsError,
)
from src.models.refresh_token import RefreshToken
from src.models.user import User
from src.models.user_channel import ChannelType, UserChannel
from src.repositories.refresh_token_repo import RefreshTokenRepository
from src.repositories.user_repo import UserRepository
from src.schemas.auth import (
    AuthResponse,
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from src.schemas.user import UserRegister
from src.services.security import (
    access_token_expires_in_seconds,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


class AuthService:
    """Сервис для управления пользователями и аутентификацией."""

    def __init__(
            self, 
            user_repo: UserRepository, 
            refresh_token_repo: RefreshTokenRepository
        ) -> None:
        self.user_repo = user_repo
        self.refresh_token_repo = refresh_token_repo

    def _now(self) -> datetime:
        return datetime.now(UTC)

    async def _issue_tokens(self, user_id: UUID) -> TokenResponse:
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token()

        await self.refresh_token_repo.create(
            RefreshToken(
                user_id=user_id,
                token_hash=hash_refresh_token(refresh_token),
                expires_at=self._now() + timedelta(days=30),
            )
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=access_token_expires_in_seconds(),
        )

    async def _get_user_for_login(self, login: str) -> User | None:
        user = await self.user_repo.get_by_username(login)
        if user:
            return user

        return await self.user_repo.get_by_email(login)

    async def register(self, user_register: UserRegister) -> AuthResponse:
        existing = await self.user_repo.get_by_email(user_register.email)
        if existing:
            raise EmailAlreadyExistsError()

        existing = await self.user_repo.get_by_username(user_register.username)
        if existing:
            raise UsernameAlreadyExistsError()

        password_hash = hash_password(user_register.password)
        user_data = user_register.model_dump(exclude={"password"})

        created_user = User(**user_data, password_hash=password_hash)
        await self.user_repo.create(created_user)

        self.user_repo.session.add(
            UserChannel(
                user_id=created_user.id,
                channel=ChannelType.EMAIL,
                is_enabled=True,
            )
        )

        if user_register.telegram_id:
            self.user_repo.session.add(
                UserChannel(
                    user_id=created_user.id,
                    channel=ChannelType.TELEGRAM,
                    is_enabled=True,
                )
            )

        token_response = await self._issue_tokens(created_user.id)
        
        return AuthResponse(user=created_user, tokens=token_response)
    
    async def login(
        self,
        username_or_email: str,
        password: str,
    ) -> TokenResponse:
        user = await self._get_user_for_login(username_or_email)

        if not user or not user.is_active:
            raise InvalidCredentialsError()

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        return await self._issue_tokens(user.id)

    async def refresh(self, request: RefreshTokenRequest) -> TokenResponse:
        token_hash = hash_refresh_token(request.refresh_token)
        refresh_token = await self.refresh_token_repo.get_by_token_hash(token_hash)

        if refresh_token is None:
            raise InvalidTokenError()

        now = self._now()

        # Revoke все токены пользователя, т.к возврат старого выглядит подозрительно
        if refresh_token.revoked_at is not None:
            await self.refresh_token_repo.revoke_active_tokens_by_user_id(
                refresh_token.user_id,
                now,
            )
            raise InvalidTokenError()

        if refresh_token.expires_at <= now:
            await self.refresh_token_repo.revoke(refresh_token, now)
            raise InvalidTokenError()

        user = await self.user_repo.get(refresh_token.user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError()

        await self.refresh_token_repo.revoke(refresh_token, now)
        return await self._issue_tokens(user.id)

    async def logout(self, request: LogoutRequest) -> None:
        token_hash = hash_refresh_token(request.refresh_token)
        refresh_token = await self.refresh_token_repo.get_by_token_hash(token_hash)

        if refresh_token is not None and refresh_token.revoked_at is None:
            await self.refresh_token_repo.revoke(refresh_token, self._now())
