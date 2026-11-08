# Deployment Guide

> Deploying the AI Paper Research Agent to production.

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Deployment Architecture](#deployment-architecture)
- [Option A: Docker Compose (Single Server)](#option-a-docker-compose-single-server)
- [Option B: Platform Deployments](#option-b-platform-deployments)
  - [Backend: Fly.io](#backend-flyio)
  - [Frontend: Vercel](#frontend-vercel)
- [Supabase Setup (Production)](#supabase-setup-production)
- [Environment Variables Checklist](#environment-variables-checklist)
- [Health Checks & Monitoring](#health-checks--monitoring)
- [Backup & Recovery](#backup--recovery)
- [Scaling Considerations](#scaling-considerations)
- [Cost Estimation](#cost-estimation)

---

## Overview

The AI Paper Research Agent has three deployable components:

| Component | Recommended Platform | Alternative |
|-----------|---------------------|-------------|
| **Frontend** (Next.js) | Vercel | Docker, any Node.js host |
| **Backend** (FastAPI) | Fly.io / Railway | Docker, any cloud VM |
| **Database** (Supabase) | Supabase (managed) | Self-hosted Postgres |

The platform approach is recommended for production. The Docker Compose approach is simpler but puts everything on one server.

---

## Prerequisites

Before deploying, ensure you have:

### Accounts & API Keys
- [Supabase](https://supabase.com) project with the reviewed migrations applied and tenant policies verified
- [OpenRouter](https://openrouter.ai) API key (`OPENROUTER_API_KEY`)
- [OpenAI](https://platform.openai.com) API key (`OPENAI_API_KEY`) — required for embeddings
- [Fly.io](https://fly.io) account (if using Fly.io for backend)
- [Vercel](https://vercel.com) account (if using Vercel for frontend)

### Optional API Keys (features degrade gracefully)
- [Anthropic](https://console.anthropic.com) API key — direct Claude fallback
- [Google AI](https://aistudio.google.com) API key — Gemini fallback
- [Mistral](https://console.mistral.ai) API key — Mistral fallback
- [Firecrawl](https://firecrawl.dev) API key — full paper text extraction
- [Semantic Scholar](https://api.semanticscholar.org) API key — citation graph (higher rate limits)
- [Mem0](https://mem0.ai) API key — user memory personalisation

### CLI Tools
```bash
# Fly.io CLI
curl -L https://fly.io/install.sh | sh

# Vercel CLI
npm i -g vercel

# Supabase CLI (optional, for local dev)
npm i -g supabase
```

---

## Deployment Architecture

```
                    ┌──────────────────┐
                    │    Vercel CDN     │
                    │ (Next.js static   │
                    │  + SSR)           │
                    └────────┬─────────┘
                             │ HTTPS
                    ┌────────▼─────────┐
                    │   Fly.io / VM    │
                    │  (FastAPI + SSE  │
                    │   + Redis)       │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───┐  ┌──────▼──────┐  ┌────▼──────┐
     │  Supabase   │  │  OpenRouter │  │  External  │
     │  (DB+Auth)  │  │  (LLM)      │  │  APIs      │
     └────────────┘  └─────────────┘  └───────────┘
```

---

## Option A: Docker Compose (Single Server)

Best for: staging, small-scale production, or if you want to manage your own server.

### 1. Prepare the Server

A Linux server (Ubuntu 22.04+) with:
- 2+ vCPUs
- 4 GB RAM minimum (8 GB recommended for LLM workloads)
- 20 GB SSD

Install Docker and Docker Compose:
```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

### 2. Clone & Configure

```bash
git clone <repo-url> /opt/paper-agent
cd /opt/paper-agent

# Create production .env file
cp .env.example .env
# Fill in ALL values (see checklist below)
```

### 3. Start with Production Compose

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The production compose file:
- Exposes the frontend on port 3000, backend on port 8000
- Passes all environment variables explicitly (not just via `env_file`)
- Includes health checks for the backend
- Sets memory limits on the backend container (2 GB)

### 4. Set Up Reverse Proxy (nginx)

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Critical for SSE streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}

server {
    listen 80;
    server_name app.yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 5. Enable SSL

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com -d app.yourdomain.com
```

---

## Option B: Platform Deployments

### Backend: Fly.io

Fly.io runs Docker containers close to your users on their global edge network. The backend already has a `Dockerfile` suitable for Fly.io.

#### 1. Create the App

```bash
cd backend
fly launch --name ai-paper-agent-backend --region iad
```

When prompted:
- Choose to deploy now? **No** (we need to set secrets first)
- Choose a Postgres? **No** (we use Supabase)
- Configure managed Redis. Production requires `REDIS_URL` for shared rate limits, per-user budgets, queue recovery, scheduler leases, and worker leases. Supabase Postgres stores canonical run records/events; `DATABASE_URL` enables durable LangGraph checkpoints. Production startup fails if graph checkpointing is not configured. In-memory stores are development-only.

#### 2. Set Secrets

```bash
fly secrets set \
  OPENROUTER_API_KEY="sk-or-v1-..." \
  OPENAI_API_KEY="sk-..." \
  SUPABASE_URL="https://yourproject.supabase.co" \
  SUPABASE_SERVICE_ROLE_KEY="eyJ..." \
  SUPABASE_JWT_SECRET="your-jwt-secret" \
  APP_URL="https://your-frontend-domain.vercel.app" \
  REDIS_URL="redis://your-redis:6379" \
  DATABASE_URL="postgresql://zenith_app:***@your-db-host:5432/postgres?sslmode=require"

# Optional
fly secrets set \
  ANTHROPIC_API_KEY="sk-ant-..." \
  GOOGLE_API_KEY="..." \
  MISTRAL_API_KEY="..." \
  FIRECRAWL_API_KEY="fc-..." \
  MEM0_API_KEY="..."
```

#### 3. Configure fly.toml

Use the checked-in `backend/fly.toml`; it sets `APP_ENV=production` and uses `/api/ready` for dependency checks. Configure Redis and Supabase secrets before deployment.

```toml
app = "ai-paper-agent-backend"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 1

  [[http_service.checks]]
    method = "GET"
    path = "/api/ready"
    interval = "15s"
    timeout = "5s"
    grace_period = "10s"

[[vm]]
  size = "shared-cpu-2x"  # 4 GB RAM recommended
```

#### 4. Deploy

```bash
fly deploy
```

#### 5. Scale

```bash
# Scale to 2 instances for high availability
fly scale count 2

# Or scale vertically
fly scale vm performance-2x
```

---

### Frontend: Vercel

#### 1. Install Vercel CLI and Deploy

```bash
cd frontend
vercel
```

Follow the prompts:
- Set up and deploy? **Yes**
- Which scope? Your team/account
- Link to existing project? **No**
- Project name: `paper-agent-frontend`
- Directory: `./`
- Override settings? **No**

#### 2. Set Environment Variables

In the Vercel dashboard (or via CLI):

```bash
vercel env add NEXT_PUBLIC_API_URL production
# Enter: https://ai-paper-agent-backend.fly.dev

vercel env add NEXT_PUBLIC_SUPABASE_URL production
# Enter: https://yourproject.supabase.co

vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production
# Enter: eyJ... (your Supabase anon key)

# Never add SUPABASE_SERVICE_ROLE_KEY to Vercel — the frontend must only
# ever see the anon key. The service role key belongs on the backend only.
```

#### 3. Configure vercel.json

Create `frontend/vercel.json` if it doesn't exist:

```json
{
  "buildCommand": "next build",
  "installCommand": "npm install",
  "framework": "nextjs"
}
```

#### 4. Redeploy with Environment Variables

```bash
vercel --prod
```

#### 5. Set Up Custom Domain

In the Vercel dashboard: **Settings > Domains > Add Domain**

---

## Supabase Setup (Production)

### 1. Create Production Project

Create a separate Supabase project for production (do not use your dev project).

### 2. Apply Schema

Apply the ordered `supabase/migrations/` against staging first, then production, using the migration runbook. Treat `schema.sql` as a schema reference snapshot.

### 3. Configure Auth

In **Authentication > Settings**:
- Set **Site URL** to your frontend URL (e.g. `https://app.yourdomain.com`)
- Add redirect URLs for your domain

In **Authentication > Providers**:
- Enable Email auth (with email confirmation for production)
- Optionally enable Google and GitHub OAuth

### 4. Get Credentials

From **Project Settings > API**:
- Project URL → `SUPABASE_URL`
- `anon` public key → `SUPABASE_ANON_KEY`
- `service_role` key → `SUPABASE_SERVICE_ROLE_KEY`

From **Project Settings > API > JWT Settings**:
- JWT Secret → `SUPABASE_JWT_SECRET`

### 5. Apply and Verify Migrations

Apply the reviewed migration sequence from `supabase/migrations/` in staging first, then production. Do not rely on `schema.sql` alone. Verify owner/member/outsider/anonymous behavior with `docs/security/SECURITY_TEST_PLAN.md` before serving users. Migration files do not prove the database has been updated.

---

## Environment Variables Checklist

Before deploying to production, ensure ALL of these are set:

### Backend (Fly.io Secrets / Docker .env)

```
# Required
OPENROUTER_API_KEY=<your key>
SUPABASE_URL=<your project url>
SUPABASE_SERVICE_ROLE_KEY=<service_role key>
SUPABASE_JWT_SECRET=<jwt secret>

# Required for embeddings
OPENAI_API_KEY=<your key>

# App
APP_URL=https://your-frontend-domain.com

# Redis (required in production)
REDIS_URL=redis://your-redis:6379

# Optional but recommended
ANTHROPIC_API_KEY=<your key>
FIRECRAWL_API_KEY=<your key>
MEM0_API_KEY=<your key>

# Optional
GOOGLE_API_KEY=<your key>
MISTRAL_API_KEY=<your key>
SEMANTIC_SCHOLAR_API_KEY=<your key>
```

### Frontend (Vercel Environment Variables)

```
NEXT_PUBLIC_API_URL=https://your-backend-domain.com
NEXT_PUBLIC_SUPABASE_URL=https://yourproject.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>
```

---

## Health Checks & Monitoring

### Backend Health

`GET /api/health` is a liveness endpoint. `GET /api/ready` performs bounded reachability checks against Supabase, Redis, the canonical Postgres run store, and the live LangGraph checkpoint connection; it returns 503 when any required production dependency is unavailable.

```bash
curl https://api.yourdomain.com/api/ready
# {"status":"ready","checks":{"supabase":true,"redis":true,"run_store":true,"graph_checkpointer":true}}
```

**Monitoring recommendations:**
- Set up an uptime monitor hitting `/api/ready` every minute
- Alert when readiness is not `ready` or response takes > 5 seconds
- Monitor `X-Response-Time` header from the `TimingMiddleware` for latency trends

### Docker Health Check

The production Docker Compose includes a health check:
```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/ready')"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

### Logging

The backend uses structured logging via `logging_config.py`. Logs include timestamps, log level, module name, and message. In production:
- Ship logs to a central aggregator (Datadog, Logtail, Papertrail)
- Set up alerts for ERROR-level log entries
- Monitor slow API responses via `TimingMiddleware` (logged at INFO level)

---

## Backup & Recovery

### Database (Supabase)

Supabase automatically backs up your data. For additional safety:

1. **Enable Point-in-Time Recovery** in Supabase dashboard (requires Pro/Team plan)
2. **Manual backup** via pg_dump:

```bash
pg_dump postgresql://postgres:<password>@db.yourproject.supabase.co:5432/postgres \
  --file=backup-$(date +%Y%m%d).sql
```

3. **Scheduled backups**: Run pg_dump as a GitHub Actions scheduled workflow:

```yaml
name: Daily DB Backup
on:
  schedule:
    - cron: '0 6 * * *'  # 6 AM UTC daily
jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          PGPASSWORD=${{ secrets.SUPABASE_DB_PASSWORD }} pg_dump \
            -h db.${{ secrets.SUPABASE_PROJECT_REF }}.supabase.co \
            -U postgres -d postgres \
            --file=backup-$(date +%Y%m%d).sql
      - uses: actions/upload-artifact@v4
        with:
          name: db-backup
          path: backup-*.sql
          retention-days: 30
```

### Rollback

#### Fly.io

```bash
# List previous deployments (machines)
fly releases

# Rollback to a specific release
fly deploy --image registry.fly.io/paper-agent-api:deployment-<id>
```

#### Vercel

In the Vercel dashboard: **Deployments → [previous deployment] → Promote to Production**

#### Docker Compose

```bash
# Stop all services
docker compose -f docker-compose.prod.yml down

# Checkout the previous version
git checkout <previous-commit-hash>

# Rebuild and start
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Scaling Considerations

### Backend (FastAPI)

The backend is primarily I/O-bound (waiting on OpenRouter, ArXiv, Supabase). Scaling approaches:

| Approach | When to use |
|----------|-------------|
| More instances (horizontal) | High concurrent user count |
| Larger VM (vertical) | Single long-running agent runs (LLM calls) |
| Postgres for run metadata/events | Durable run history across restarts and replicas |
| Redis for queue and leases | Shared work delivery, rate limits, budgets, and scheduler/worker leases |

**Fly.io scaling:**
```bash
# Run 2-4 instances behind load balancer
fly scale count 4

# Ensure REDIS_URL is set for shared queues, limits, budgets, and leases
```

Production requires reachable Supabase Postgres, direct Postgres `DATABASE_URL`, and Redis, even with one backend instance. Supabase Postgres is canonical for run metadata, results, and events; the direct Postgres connection stores LangGraph checkpoints. Redis Streams carry jobs, while Redis leases coordinate workers and scheduled ingestion. Startup initializes the LangGraph checkpoint schema and fails closed if unavailable. The API fails readiness if required dependencies are unreachable or run-store migration RPCs are missing. The backend enforces `LANGGRAPH_STRICT_MSGPACK=true` before importing LangGraph to restrict checkpoint deserialization.

### Frontend (Next.js)

Vercel automatically scales the frontend. For custom Docker deployments, use a load balancer (nginx, HAProxy) with sticky sessions.

### Database (Supabase)

Supabase Pro/Team plans offer:
- Higher connection limits
- Point-in-time recovery
- Read replicas
- Larger compute instances

Monitor connection counts in the Supabase dashboard. If approaching limits:
1. Enable connection pooling (PgBouncer) in Supabase settings
2. Upgrade to a larger compute plan
3. Add read replicas for heavy read workloads

### Rate Limits

Production rate limits are applied by `slowapi`:

| Endpoint | Limit |
|----------|-------|
| `/api/search` | 10 req / minute |
| `/api/stream/*` | 20 req / minute |
| All others | 60 req / minute |

These limits are **per IP address** by default (using `get_remote_address`). Behind a reverse proxy, ensure `X-Forwarded-For` is being forwarded correctly, or adjust the key function in `backend/middleware/rate_limit.py`.

### LLM Cost Management

LLM API calls are the primary cost driver. Mitigation strategies already implemented:

1. **Caching** — Paper summaries and embeddings are cached in Supabase
2. **Tiered models** — Fast/cheap models for pre-filtering (GPT-4o-mini), expensive models only for final summaries (Claude Sonnet)
3. **Token limits** — `max_tokens=4096` on all LLM calls
4. **Model selection** — Users can choose cheaper models via the ModelSelector

Additional production safeguards to consider:
- Set spending limits on your OpenRouter account
- Monitor per-user API usage and set caps
- Batch summary generation in off-peak hours (already supported via `daily_fetch.py`)

---

## Cost Estimation

Approximate monthly costs for a small production deployment:

| Service | Tier | Est. Monthly Cost |
|---------|------|-------------------|
| Supabase | Free / Pro ($25) | $0–$25 |
| Fly.io | shared-cpu-2x ($31/mo) | ~$31 |
| Vercel | Hobby / Pro ($20) | $0–$20 |
| OpenRouter | Pay-per-token | $10–$50 |
| OpenAI (embeddings) | Pay-per-token | $1–$5 |
| Redis (Fly Upstash) | Free tier | $0 |
| **Total** | | **$42–$131/mo** |

API costs scale with usage. The main variables are:
- Number of papers summarised per day
- Embedding calls (one per new paper)
- Direct provider fallback calls (if OpenRouter is down)
