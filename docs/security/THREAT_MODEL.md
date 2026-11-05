# Threat Model — Zenith

Assets: user accounts, saved papers/prefs, Mem0 memories, paper corpus + embeddings, LLM spend, crawled full text, run results, (future) project sources/uploads.
Actors: anonymous internet, authenticated user (malicious or compromised), malicious paper/author, compromised upstream API (arXiv/HF/PWC/S2/Firecrawl), provider outage.
Trust boundaries: browser→FastAPI (JWT/SSE token) → Supabase (service-role today ⚠) → Redis → LLM providers → external pages/PDFs → (future) GitHub/MCP/sandbox.
STRIDE/abuse cases: spoofed JWT (alg confusion, cross-project token) → §5.2 allowlist + iss/aud; IDOR on run_id/paper saves → ownership checks + RLS; SSRF via paper URL/PWC `repositories` → SSRF validator; prompt injection via paper text / saved title → delimiters + sanitize + structured output; wallet drain via anonymous search / reconnect loops → auth + quotas + start-once; info disclosure via `str(e)` errors / Langfuse traces → generic errors + redaction; cache poisoning via `crawled_content` keyed by paper_id only → key by (paper_id,url,parser_version).
Residual risk: service-role still used until user-scoped client lands; PWC liveness unverified; Langfuse redaction pending.
