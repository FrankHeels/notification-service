from datetime import UTC, datetime
from uuid import uuid4

import jwt

from src.config import settings
from src.services.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_password_hash_does_not_store_plain_password():
    password = "correct horse battery staple"

    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash) is True
    assert verify_password("wrong password", password_hash) is False


def test_access_token_contains_required_claims():
    user_id = uuid4()

    token = create_access_token(user_id)
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"
    assert payload["jti"]
    assert datetime.fromtimestamp(payload["exp"], UTC) > datetime.now(UTC)


def test_refresh_token_hash_is_deterministic_and_does_not_store_plain_token():
    refresh_token = create_refresh_token()

    token_hash = hash_refresh_token(refresh_token)

    assert token_hash != refresh_token
    assert token_hash == hash_refresh_token(refresh_token)
    assert len(token_hash) == 64
