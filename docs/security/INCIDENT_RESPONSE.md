# Incident Response

Detect (Sentry/Langfuse alerts, 5xx spike, cost anomaly) → Contain (disable key/endpoint via env, revoke Supabase session) → Rotate (Supabase JWT secret / service-role / provider keys per `.env.example` rotation runbook) → Revoke (delete compromised runs/sessions; Mem0 forget) → Notify (affected users if cross-tenant access confirmed) → Recover (restore from Supabase backups; re-run `docs/DEPLOYMENT.md` restore drill) → Postmortem filed in `docs/adr/`.
