from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.refresh_token import RefreshToken
from src.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RefreshToken, session)
    
    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()
    
    async def revoke(
            self, 
            refresh_token: RefreshToken, 
            revoke_at: datetime
    ) -> RefreshToken:
        refresh_token.revoked_at = revoke_at
        await self.session.flush()
        return refresh_token

    async def revoke_active_tokens_by_user_id(
        self,
        user_id: UUID, 
        revoke_at: datetime         
    ) -> None:
        results = await self.session.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None)   
            )
        )

        for refresh_token in results.scalars():
            refresh_token.revoked_at = revoke_at

        await self.session.flush()
