# Security Policy

> How to report vulnerabilities, what's covered, and deployment hardening.

---

## Table of Contents

- [Reporting a Vulnerability](#reporting-a-vulnerability)
- [Supported Versions](#supported-versions)
- [Security Model](#security-model)
- [Dependency Scanning](#dependency-scanning)
- [Best Practices for Deployers](#best-practices-for-deployers)

---

## Reporting a Vulnerability

If you discover a security vulnerability in the AI Paper Research Agent, **please do not open a public issue**. Instead, report it privately:

- **Email:** Send a detailed report to the project maintainers at the address listed on the repository.
- **What to include:**
  - A clear description of the vulnerability
  - Steps to reproduce (include code snippets, URLs, or request payloads)
  - The affected component and version
  - Potential impact (data exposure, privilege escalation, denial of service, etc.)
  - Any suggested fix (optional but appreciated)

**Response time:** We aim to acknowledge receipt within **48 hours** and provide a resolution timeline within **5 business days**. Critical vulnerabilities will be triaged immediately.

**Disclosure:** We follow coordinated disclosure. Please allow us at least **30 days** to release a fix before publicly disclosing the vulnerability.

---

## Supported Versions

Only the latest release receives security patches. Currently:

| Version | Supported          |
|---------|--------------------|
| 0.1.0   | :white_check_mark: |

When a new version is released, the previous version will receive security patches for a **30-day transition window**, after which support ends.

---

## Security Model

The AI Paper Research Agent handles sensitive credentials (LLM API keys, Supabase keys) and user data. Here is how the project enforces security at each layer:

### API Key Isolation

- All LLM API keys (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `MISTRAL_API_KEY`) are **server-side only**. They are read exclusively by the FastAPI backend (`backend/config.py`) and are never exposed to the frontend.
- The only key shared with the frontend is `NEXT_PUBLIC_API_URL` (the backend API base URL), and `SUPABASE_ANON_KEY` (Supabase's public-anon key, designed for public exposure within Row-Level Security constraints).

### Authentication

- **Supabase Auth** handles all user management (email/password + OAuth with Google and GitHub).
- On every API call, the frontend attaches a Supabase JWT as `Authorization: Bearer <token>`.
- The FastAPI backend validates every token using `SUPABASE_JWT_SECRET` (HS256 algorithm) via `backend/dependencies.py`. Invalid or expired tokens receive a `401 Unauthorized`.
- The `user_id` extracted from the JWT is used as the Mem0 user key and for filtering saved papers in Supabase.
- Token validation is applied to every `/api/*` endpoint except `GET /api/health`.

### Rate Limiting

Rate limits are enforced via `slowapi` at the backend layer to prevent abuse:

| Endpoint            | Limit          |
|---------------------|----------------|
| `POST /api/search`  | 10 req / minute |
| `GET /api/stream/*` | 20 req / minute |
| `GET /api/health`   | Exempt (unlimited) |
| All other endpoints | 60 req / minute (default) |

Rate limit exceeded responses return `HTTP 429 Too Many Requests`.

### CORS Protection

The backend CORS middleware (`backend/main.py`) restricts allowed origins. In development, this is `http://localhost:3000`. In production, this **must** be set to your actual frontend domain (e.g., `https://paperagent.app`). Credentials are enabled, and all standard methods/headers are allowed within the whitelisted origin.

### Docker Security

- No secrets are baked into Docker images. All credentials are injected at runtime via the `.env` file or environment variables.
- Docker Compose files (`docker-compose.yml`, `docker-compose.prod.yml`) reference variables from the host environment — never contain hardcoded secrets.
- Multi-stage builds are used to keep final images minimal.

### User Data & Third-Party Services

- **Mem0 (third-party):** User memory data (natural-language preferences, save/dismiss history) is stored on Mem0's servers. Mem0 auto-consolidates and deduplicates memories over time. See [Mem0's Privacy Policy](https://mem0.ai/privacy) for details on their data handling and retention.
- **Supabase (your account):** All paper data, user saved papers, and user preferences are stored in your own Supabase project. Supabase provides encryption at rest for the managed Postgres instance. Row-Level Security (RLS) policies should be reviewed and tightened for production deployments.

### LLM Data Flow

- Paper abstracts and titles are sent to LLM providers (OpenRouter, Anthropic, OpenAI, Google, Mistral) for summarisation and scoring.
- OpenRouter receives an `HTTP-Referer` header set to `APP_URL` and `X-Title` header set to `"AI Paper Research Agent"` for identification.
- Token usage is capped per agent role (`max_tokens=4096` on all LLM calls) to control costs and prevent runaway generation.

---

## Dependency Scanning

Regular dependency audits help catch known vulnerabilities before they become exploitable.

### Backend (Python)

```bash
cd backend
pip install -e ".[dev]"
pip-audit    # Check for known vulnerabilities in Python packages
```

Alternatively, use `safety`:
```bash
safety check
```

### Frontend (Node.js)

```bash
cd frontend
npm audit    # Check for known vulnerabilities in npm packages
npm audit fix   # Auto-fix non-breaking patches
```

### CI Integration

The GitHub Actions CI workflow (`ci.yml`) runs lint and type checks on every push/PR. Dependency auditing should be added as a scheduled job or pre-release gate:

```yaml
# Example addition to .github/workflows/ci.yml
security-audit:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Backend audit
      run: cd backend && pip install pip-audit && pip-audit
    - name: Frontend audit
      run: cd frontend && npm audit --audit-level=high
```

Run `pip-audit` and `npm audit` before each release. Fix critical and high-severity findings immediately.

---

## Best Practices for Deployers

Follow this checklist when deploying to production:

### Environment & Credentials

- [ ] **Rotate all API keys** before going to production — generate fresh keys for OpenRouter, Anthropic, OpenAI, Google, Mistral, Firecrawl, and Mem0.
- [ ] **Use a strong `SUPABASE_JWT_SECRET`**. Generate with: `openssl rand -hex 64`. This secret must be at least 256 bits (32 bytes) and must match the JWT secret configured in your Supabase project dashboard.
- [ ] **Never commit `.env` to version control.** The file is already in `.gitignore` — verify it is not accidentally staged.
- [ ] **Use a secrets manager** (e.g., Fly.io secrets, Vercel environment variables, Railway variables) rather than `.env` files on production servers.

### CORS & Networking

- [ ] **Restrict CORS origins** in production. Update the `allow_origins` list in `backend/main.py` to include only your actual frontend domain(s). Never use `["*"]` in production.
- [ ] **Enable HTTPS** for all external traffic. The frontend (Vercel) and Supabase provide TLS by default. If self-hosting the backend, put it behind a reverse proxy (nginx, Caddy) that terminates TLS.
- [ ] **Use a dedicated Redis instance** with authentication. Set `REDIS_URL` with a password (e.g., `redis://:password@host:6379`). Otherwise, the system falls back to in-memory run state storage, which is lost on restart and incompatible with multi-instance deployments.

### Database

- [ ] **Review Row-Level Security (RLS) policies** on your Supabase tables. The `schema.sql` creates tables but does not define RLS policies — you must add them manually via the Supabase dashboard or SQL editor.
- [ ] **Enable backups** for your Supabase project (available on Pro plan and above).
- [ ] **Use the Supabase service role key** (`SUPABASE_SERVICE_ROLE_KEY`) only in the backend — never expose it in client-side code. The frontend should only use `SUPABASE_ANON_KEY`.

### Monitoring

- [ ] **Set up alerting** for unusual rate limit violations or 5xx error spikes.
- [ ] **Monitor LLM API costs** via OpenRouter's dashboard. Set spending limits to prevent unexpected charges.
- [ ] **Log security events** (failed auth attempts, rate limit hits) for review.

---

> **Need help?** If you have questions about hardening a deployment, open a discussion on the repository or consult [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) for step-by-step production deployment instructions.
