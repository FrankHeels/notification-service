import argparse
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from src.config import settings


def create_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a test JWT for an existing user_id."
    )
    parser.add_argument("user_id", type=UUID)
    args = parser.parse_args()

    token = create_token(args.user_id)
    print(token)
    print()
    print(f"Authorization: Bearer {token}")


if __name__ == "__main__":
    main()
