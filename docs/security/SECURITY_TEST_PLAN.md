# Security Test Plan

Regression cases (all in `backend/tests/test_security.py` or follow-ups): alg=none rejected; wrong iss/aud rejected; unknown-kid JWKS refetch; cross-user run streaming → 404; reconnect does not restart orchestrator; SSRF private/loopback/metadata URLs blocked; unknown model override rejected; upstream DB errors not leaked to client. Manual/periodic: RLS owner/member/outsider/anon matrix against staging Supabase; pentest of SSE token + proxy headers; dependency/container scans in CI.
