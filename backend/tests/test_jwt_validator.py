import base64
from datetime import datetime, timedelta, timezone

import pytest
import jwt
from jwt.exceptions import InvalidTokenError
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from services import jwt_validator


def _b64u(value: int) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(32, "big")).rstrip(b"=").decode()


@pytest.fixture
def ec_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "alg": "ES256",
        "kid": "test-kid",
        "x": _b64u(public_numbers.x),
        "y": _b64u(public_numbers.y),
    }
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return jwk, pem


def _set_env(monkeypatch, **values):
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


@pytest.mark.asyncio
async def test_hs256_legacy_path(monkeypatch):
    _set_env(
        monkeypatch,
        SUPABASE_URL="",
        SUPABASE_JWT_SECRET="legacy-secret-that-is-long-enough-for-hs256",
    )
    token = jwt.encode(
        {"sub": "user-1", "email": "a@b.c"},
        "legacy-secret-that-is-long-enough-for-hs256",
        algorithm="HS256",
    )
    payload = await jwt_validator.decode_supabase_token(token)
    assert payload["sub"] == "user-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_claim", ["exp", "iss", "aud"])
async def test_production_hs256_requires_supabase_identity_and_expiry_claims(
    monkeypatch, missing_claim
):
    secret = "production-secret-that-is-long-enough-for-hs256"
    _set_env(
        monkeypatch,
        APP_ENV="production",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_SECRET=secret,
    )
    payload = {
        "sub": "user-1",
        "iss": "https://example.supabase.co/auth/v1",
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    payload.pop(missing_claim)
    token = jwt.encode(payload, secret, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        await jwt_validator.decode_supabase_token(token)


@pytest.mark.asyncio
async def test_production_hs256_accepts_valid_supabase_claims(monkeypatch):
    secret = "production-secret-that-is-long-enough-for-hs256"
    _set_env(
        monkeypatch,
        APP_ENV="production",
        SUPABASE_URL="https://example.supabase.co/",
        SUPABASE_JWT_SECRET=secret,
    )
    token = jwt.encode(
        {
            "sub": "user-1",
            "iss": "https://example.supabase.co/auth/v1",
            "aud": "authenticated",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )

    payload = await jwt_validator.decode_supabase_token(token)
    assert payload["sub"] == "user-1"


@pytest.mark.asyncio
async def test_es256_jwks_path(monkeypatch, ec_keypair):
    jwk, pem = ec_keypair
    _set_env(
        monkeypatch,
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_SECRET="legacy-secret-that-is-long-enough-for-hs256",  # must NOT be used for ES256 token
    )
    token = jwt.encode({"sub": "user-2"}, pem, algorithm="ES256", headers={"kid": "test-kid"})

    async def fake_fetch(url):
        return [jwk]

    monkeypatch.setattr(jwt_validator, "_fetch_jwks", fake_fetch)
    payload = await jwt_validator.decode_supabase_token(token)
    assert payload["sub"] == "user-2"


@pytest.mark.asyncio
async def test_es256_unknown_kid_rejected(monkeypatch, ec_keypair):
    jwk, pem = ec_keypair
    _set_env(
        monkeypatch,
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_SECRET="legacy-secret-that-is-long-enough-for-hs256",
    )
    token = jwt.encode({"sub": "user-3"}, pem, algorithm="ES256", headers={"kid": "other-kid"})

    async def fake_fetch(url):
        return [jwk]

    monkeypatch.setattr(jwt_validator, "_fetch_jwks", fake_fetch)
    with pytest.raises(InvalidTokenError):
        await jwt_validator.decode_supabase_token(token)


@pytest.mark.asyncio
async def test_not_configured_rejected(monkeypatch):
    _set_env(monkeypatch, SUPABASE_URL=None, SUPABASE_JWT_SECRET=None)
    token = jwt.encode(
        {"sub": "user"},
        "irrelevant-key-that-is-long-enough-for-hs256",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        await jwt_validator.decode_supabase_token(token)


@pytest.mark.asyncio
async def test_invalid_token_rejected(monkeypatch):
    _set_env(
        monkeypatch,
        SUPABASE_URL=None,
        SUPABASE_JWT_SECRET="test-secret-that-is-long-enough-for-hs256",
    )
    with pytest.raises(InvalidTokenError):
        await jwt_validator.decode_supabase_token("not-a-jwt")


@pytest.mark.asyncio
async def test_unsupported_token_type_is_rejected(monkeypatch):
    secret = "test-secret-that-is-long-enough-for-hs256"
    _set_env(monkeypatch, APP_ENV="development", SUPABASE_JWT_SECRET=secret)
    token = jwt.encode(
        {"sub": "user-1"}, secret, algorithm="HS256", headers={"typ": "JOSE"}
    )

    with pytest.raises(InvalidTokenError, match="Unsupported token type"):
        await jwt_validator.decode_supabase_token(token)
