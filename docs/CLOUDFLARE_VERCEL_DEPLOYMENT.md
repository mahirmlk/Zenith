# Cloudflare backend and Vercel frontend

This repository includes a local deployment scaffold under
[`cloudflare/worker/`](../cloudflare/worker/). The Worker forwards the existing
`backend/Dockerfile` image on port 8000 through one named Durable Object
Container. It passes request bodies and response streams through without
buffering, including Server-Sent Events. It probes `/api/ready` before the
first forwarded request and sends a one-minute heartbeat to keep the singleton
warm.

## Platform prerequisites and limits

- Cloudflare Containers require the Workers Paid plan. The Durable Object
Container scheduling policy used here is a public beta; API and operational
behavior may change.
- The Worker uses one stable Durable Object name and one backend process. This
prevents duplicate FastAPI lifespan workers but provides no horizontal backend
replicas. Capacity and failover behavior must be proven with expected traffic
before production use.
- The `standard-1` instance provides 1/2 vCPU, 4 GiB memory, and 8 GB disk.
Cloudflare bills Container memory, CPU, disk, Worker, Durable Object, egress,
and observability usage separately under its current plan. The one-minute
heartbeat resets a 150-second inactivity timer, so it keeps roughly 4 GiB
allocated continuously. At the currently documented memory rate, that is
about 2,880 GiB-hours monthly and approximately $25.70 in memory charges after
the Workers Paid plan's included 25 GiB-hours, before CPU, Durable Object,
Worker, egress, and logging charges. See [Cloudflare Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/).
- The cron schedule may take several minutes to propagate. A Worker deployment
can exist before the Container is provisioned; early requests can return 503
while the backend starts. The proxy waits for `/api/ready` and retries startup
probes for up to 80 attempts. Each probe can take up to 3 seconds, with 500 ms
between attempts, so the worst case is about 4 minutes 40 seconds. Callers
should retry cold-start 503 responses with backoff.
- Durable Objects route a singleton to one location. This architecture favors
single-process correctness over multi-region capacity; measure latency from
Vercel regions and expected concurrent SSE users before launch.

## Configure Cloudflare

1. Install Node.js, npm, and Docker. Cloudflare builds the image from the
   Wrangler config's `build_context: ../../backend`, using
   `backend/Dockerfile`. That Docker build context contains `pyproject.toml`,
   `uv.lock`, and the application files expected by the existing Dockerfile.
2. In `cloudflare/worker/`, run `npm install`, `npm run types`, and
   `npm run typecheck`. `npm run deploy:dry-run` bundles Worker code only; a
   real Container build requires Docker and an authenticated Cloudflare
   account.
3. Configure the required Worker secrets in Cloudflare without checking their
   values into git. Required names are `APP_URL`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY`, `REDIS_URL`, and `DATABASE_URL`. Wrangler
   refuses deployment if a required secret is missing. `APP_URL` is the exact
   public Vercel origin. Set `REDIS_URL` to a reachable Redis TLS endpoint and
   `DATABASE_URL` to a supported Supabase Postgres connection with SSL.
4. Configure optional runtime secrets as needed: `OPENROUTER_API_KEY`,
   `OPENAI_API_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`,
   `SEMANTIC_SCHOLAR_API_KEY`, and observability/provider credentials. Only
   configured bindings are copied to the Container. The Worker sets
   `APP_ENV=production` and `LANGGRAPH_STRICT_MSGPACK=true` itself.
5. Add `CORS_ORIGINS` as the exact comma-separated browser-origin list. Keep
   it aligned with the Vercel custom domain and `APP_URL`.
6. Deploy the Worker, wait for Container provisioning, and set the API custom
   domain in Cloudflare (for example, `api.<your-domain>`). Keep the Vercel
   origin separate. Monitor `/api/ready`, Worker logs, Container logs, memory,
   egress, and SSE connection behavior.

Required deployment secrets should be entered with `npx wrangler secret put
NAME` from the Worker directory or through the Cloudflare dashboard. Optional
secrets should be entered the same way. Never put secret values into
`wrangler.jsonc`, source files, or this guide. Rotating a Worker secret does
not mutate an already running Container's environment; restart/redeploy the
Worker version and confirm the next Container startup receives the new value.

### AI and feature gates

The backend can pass readiness with model features gated off. To enable metered
AI search/summary calls, configure `LLM_ENABLED=true`, `OPENROUTER_API_KEY`,
`OPENAI_API_KEY`, positive `LLM_DAILY_SPEND_CAP_USD_MICROS` and
`LLM_MONTHLY_SPEND_CAP_USD_MICROS`, and verify migration 0023's spend-meter
RPCs against staging. Reconcile metering against provider usage before enabling
model-backed features for real users. Do not enable these gates with
placeholder credentials or zero spend caps.

Keep `RESEARCH_SYNTHESIS_ENABLED`, `RESEARCH_PLAN_EXECUTION_ENABLED`,
`PUBLIC_PAPER_EVIDENCE_ENABLED`, `OCR_ENABLED`, `NOTIFICATIONS_EMAIL_ENABLED`,
and `SANDBOX_ENABLED` false for the first deployment unless their respective
staging authorization, recovery, provider, and quality gates have passed. For
email digests, add the Resend and unsubscribe settings from `.env.example` and
verify delivery/webhooks in staging first.

## Configure Vercel and Supabase Auth

Set these Vercel **production** environment variables, then create a new
production deployment:

```text
NEXT_PUBLIC_API_URL=https://<cloudflare-api-domain>
NEXT_PUBLIC_SUPABASE_URL=https://<supabase-project>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase-anon-key>
```

Do not add `SUPABASE_SERVICE_ROLE_KEY` or other backend credentials to Vercel.
The frontend uses the public Supabase anon key; the API and Container hold the
service key.

In Supabase Auth, set the production Site URL to the Vercel custom domain,
configure the email confirmation and invitation templates, and allow the
exact callback and project-invitation URLs listed in [the deployment guide](DEPLOYMENT.md).
Ensure the frontend sends the Supabase bearer token to the Cloudflare API
domain and verify the Vercel origin against backend CORS settings.

## Staging gate before production

Use a separate non-production Supabase project, Redis, and provider accounts.
Apply migrations `0001`–`0034` to staging using
[`MIGRATIONS_RUNBOOK.md`](MIGRATIONS_RUNBOOK.md). Verify RLS across owner,
member, editor, viewer, outsider, and anonymous sessions; run migrations and
rollback checks; exercise account deletion, run recovery, checkpoint restore,
provider-meter failure/retry cases, invitation/Auth redirects, and benchmark
watch baseline/delta behavior. Smoke test the Worker directly, Vercel login and
API requests, multi-minute SSE delivery, early startup/503 recovery, and the
scheduled heartbeat. Capture backups and complete a restore exercise. Do not
label this setup production-ready until those checks and current-head CI are
green.

## Current Cloudflare API basis

The implementation follows Cloudflare's current docs for [Wrangler Container
configuration](https://developers.cloudflare.com/containers/configuration/wrangler/),
[the Durable Object Container API](https://developers.cloudflare.com/containers/api/durable-object-container/),
[request forwarding and secret-to-Container environment](https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/),
[Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/),
[Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/),
[instance sizes](https://developers.cloudflare.com/containers/platform/limits/),
and [Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/).
