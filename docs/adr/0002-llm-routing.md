# ADR-002: OpenRouter-Primary LLM Routing with Direct Provider Fallbacks

**Status:** Accepted

## Context

The agent needs to summarise papers, score relevance, and rank results — all LLM workloads. Options:

- **Single provider (OpenRouter):** one key, one contract, broad model access — but a single point of failure and no way to pick cheaper models.
- **Direct provider calls only:** N keys and N SDKs, more moving parts, and harder to swap models.
- **OpenRouter-first with direct fallbacks:** one primary gateway plus resilient degradation when it is down or a model is unavailable.

Cost also matters: summaries dominate spend, so the routing layer must let cheaper models be chosen for bulk work.

## Decision

Use `backend/services/llm_router.py` as the **single gateway** for every LLM call in the agent layer:

- **Primary:** OpenRouter (`OPENROUTER_API_KEY`), sending `HTTP-Referer: APP_URL` and `X-Title: "AI Paper Research Agent"` for identification.
- **Fallbacks:** direct provider clients — Anthropic, OpenAI, Google Gemini, Mistral — attempted in order when the primary fails or the requested model is unavailable.
- All calls route through `llm_router.py`; no module ever initialises a provider client directly. Callers receive a model name and temperature, and the router resolves the best available provider.
- Token budgets are capped per role (`max_tokens=4096`) and the model tier is user-selectable via the `ModelSelector` (defaults to a cheap model for pre-filtering).

## Consequences

- **Positive:** One place to add providers, tune fallback order, and enforce token caps.
- **Positive:** Degrades gracefully if OpenRouter is down; users can pick cost/quality trade-offs.
- **Negative:** Adds a layer of indirection; a new provider requires a small router change rather than a caller change.
- **Negative:** LLM spend is still the dominant cost driver — mitigated by caching (see ADR-007) and per-run caps (see ADR-008).
