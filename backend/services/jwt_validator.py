"""Supabase JWT validation.

Since October 2025 new Supabase projects default to asymmetric JWTs (ES256)
signed against a public key published on the project's JWKS endpoint, rather
than the legacy shared-secret HS256 signing. This module validates tokens the
way the issuing project actually signs them:

1. Asymmetric (ES256/RS256/EdDSA) tokens are verified against the public key
   from ``{SUPABASE_URL}/auth/v1/.well-known/jwks.json``, selected by the
   ``kid`` in the token header. The JWKS is fetched lazily and cached in
   memory for an hour.
2. Legacy HS256 tokens fall back to verifying with ``SUPABASE_JWT_SECRET``.

No Supabase project should ever be validated with HS256 against a public
key, so there is no algorithmic confusion risk: an asymmetric token simply
fails the HS256 signature check.
"""
import logging
import time
from typing import Any

import httpx
import jwt
from jwt.exceptions import InvalidTokenError

from config import get_settings

logger = logging.getLogger(__name__)

JWKS_PATH = "/auth/v1/.well-known/jwks.json"
_JWKS_TTL_SECONDS = 3600  # Supabase rotates keys; refresh hourly

_JWKS_CACHE: dict[str, Any] = {"keys": None, "fetched_at": 0.0}


def invalidate_jwks_cache() -> None:
    """Drop the cached JWKS so the next decode refetches it."""
    _JWKS_CACHE["keys"] = None
    _JWKS_CACHE["fetched_at"] = 0.0


async def _fetch_jwks(supabase_url: str) -> list[dict[str, Any]]:
    now = time.monotonic()
    cached_keys = _JWKS_CACHE.get("keys")
    if isinstance(cached_keys, list) and now - _JWKS_CACHE.get("fetched_at", 0.0) < _JWKS_TTL_SECONDS:
        return cached_keys

    url = f"{supabase_url.rstrip('/')}{JWKS_PATH}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    keys: list[dict[str, Any]] = data.get("keys", [])
    _JWKS_CACHE["keys"] = keys
    _JWKS_CACHE["fetched_at"] = now
    return keys


def _find_signing_key(keys: list[dict[str, Any]], kid: str | None) -> dict[str, Any] | None:
    if not kid:
        return None
    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


async def decode_supabase_token(token: str) -> dict[str, Any]:
    """Decode and validate a Supabase JWT, returning its payload.

    Raises :class:`jwt.exceptions.InvalidTokenError` on any failure so
    callers can uniformly treat the token as invalid.
    """
    settings = get_settings()

    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError:
        raise InvalidTokenError("Invalid token header") from None

    token_type = header.get("typ")
    if token_type is not None and (
        not isinstance(token_type, str) or token_type.upper() != "JWT"
    ):
        raise InvalidTokenError("Unsupported token type")

    alg = header.get("alg")

    # Explicit alg allowlist (update.md §5.2): reject alg=none and anything
    # not a Supabase signing algorithm. HS256 is legacy-only.
    _ALLOWED_ASYMMETRIC = {"ES256", "RS256", "EdDSA"}
    if alg not in _ALLOWED_ASYMMETRIC and alg != "HS256":
        raise InvalidTokenError(f"Unsupported signing algorithm: {alg!r}")

    def _check_claims(payload: dict[str, Any]) -> dict[str, Any]:
        # Supabase user sessions include these claims. Production must reject
        # signed but incomplete tokens as well as tokens with foreign claims.
        if settings.app_env == "production":
            if not settings.supabase_url:
                raise InvalidTokenError("Supabase URL is not configured for JWT validation")
            expected_issuer = settings.supabase_url.rstrip("/") + "/auth/v1"
            if payload.get("iss") != expected_issuer:
                raise InvalidTokenError("Invalid token issuer")
            if payload.get("aud") != "authenticated":
                raise InvalidTokenError("Invalid token audience")
            if not isinstance(payload.get("sub"), str) or not payload["sub"]:
                raise InvalidTokenError("Invalid token subject")
            if "exp" not in payload:
                raise InvalidTokenError("Token expiration is required")

        # Development may use minimal, locally signed fixtures. Any issuer or
        # audience claim they do provide is still checked against Supabase.
        iss = payload.get("iss")
        if iss and settings.supabase_url:
            expected = settings.supabase_url.rstrip("/") + "/auth/v1"
            if iss != expected:
                raise InvalidTokenError("Invalid token issuer")
        aud = payload.get("aud")
        if aud:
            audiences = aud if isinstance(aud, list) else [aud]
            if not set(audiences) & {"authenticated", "service_role"}:
                raise InvalidTokenError("Invalid token audience")
        return payload

    # Asymmetric signing (new Supabase default) — verify against JWKS public key.
    if alg in _ALLOWED_ASYMMETRIC:
        if not settings.supabase_url:
            raise InvalidTokenError("Supabase URL is not configured for JWT validation")
        try:
            keys = await _fetch_jwks(settings.supabase_url)
        except Exception as exc:
            logger.warning("Failed to fetch Supabase JWKS: %s", exc)
            raise InvalidTokenError("Could not fetch signing keys") from exc
        signing_key = _find_signing_key(keys, header.get("kid"))
        if signing_key is None:
            # Possible key rotation: refetch JWKS once before rejecting.
            invalidate_jwks_cache()
            try:
                keys = await _fetch_jwks(settings.supabase_url)
            except Exception:
                keys = []
            signing_key = _find_signing_key(keys, header.get("kid"))
        if signing_key is None:
            raise InvalidTokenError("Signing key not found in JWKS")
        try:
            key = jwt.PyJWK.from_dict(signing_key)
        except Exception as exc:
            raise InvalidTokenError("Invalid signing key in JWKS") from exc
        return _check_claims(
            jwt.decode(token, key, algorithms=[alg], options={"verify_aud": False})
        )

    # Legacy shared-secret signing (HS256).
    if not settings.supabase_jwt_secret:
        raise InvalidTokenError("Supabase JWT validation is not configured")
    return _check_claims(
        jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={
                "verify_aud": False,
                "require": ["exp", "sub"] if settings.app_env == "production" else [],
            },
        )
    )
