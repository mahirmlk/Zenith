# ADR-003: Supabase JWT Validation — ES256 JWKS with HS256 Legacy Fallback

**Status:** Accepted

## Context

Since October 2025, new Supabase projects default to **asymmetric JWTs (ES256)** signed against a public key published on the project's JWKS endpoint. Older projects use **legacy shared-secret HS256** signing with `SUPABASE_JWT_SECRET`.

The original code validated every token against `SUPABASE_JWT_SECRET` (HS256 only). On new projects this rejected otherwise-valid tokens, and on projects where an HS256 secret was configured alongside a public key there was no clean upgrade path. The repo also re-exposed the validation concern as a security finding (single algorithm, secret shared with the token issuer).

## Decision

Add `backend/services/jwt_validator.py` as the single token-validation path, used by the auth dependency and middleware:

1. **Asymmetric (ES256/RS256/EdDSA)** tokens are verified against the public key fetched from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, selected by the `kid` in the token header. The JWKS is fetched lazily and cached in memory for 1 hour (`_JWKS_TTL_SECONDS = 3600`).
2. **Legacy HS256** tokens fall back to `SUPABASE_JWT_SECRET`.
3. `invalidate_jwks_cache()` exists so tests can force a refetch.

There is no algorithmic-confusion risk: an asymmetric token fails the HS256 signature check, and vice versa. `verify_aud` is disabled to match Supabase's token audience behaviour.

## Consequences

- **Positive:** Works on both new (ES256/JWKS) and legacy (HS256) Supabase projects without configuration.
- **Positive:** Public-key verification means the backend never holds the signing secret for new projects.
- **Positive:** JWKS caching keeps the per-request cost low (one HTTP fetch per hour per process).
- **Negative:** The HS256 fallback still requires `SUPABASE_JWT_SECRET`; operators should migrate legacy projects to asymmetric signing.
- **Negative:** A JWKS fetch failure (network, Supabase outage) rejects asymmetric tokens until the endpoint is reachable again — a deliberate fail-closed posture.
- **Follow-up:** If a project rotates keys more often than hourly, lower `_JWKS_TTL_SECONDS`.
