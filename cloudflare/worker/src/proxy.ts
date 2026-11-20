export const SECRET_TO_BACKEND_KEYS = [
  "APP_URL",
  "CORS_ORIGINS",
  "OPENROUTER_API_KEY",
  "OPENAI_API_KEY",
  "ANTHROPIC_API_KEY",
  "GOOGLE_API_KEY",
  "MISTRAL_API_KEY",
  "SEMANTIC_SCHOLAR_API_KEY",
  "GITHUB_TOKEN",
  "MEM0_API_KEY",
  "SUPABASE_URL",
  "SUPABASE_ANON_KEY",
  "SUPABASE_SERVICE_ROLE_KEY",
  "SUPABASE_JWT_SECRET",
  "REDIS_URL",
  "DATABASE_URL",
  "ADMIN_API_KEY",
  "MAX_SUMMARIES_PER_RUN",
  "MAX_SEARCHES_PER_DAY_PER_USER",
  "LLM_ENABLED",
  "LLM_DAILY_SPEND_CAP_USD_MICROS",
  "LLM_MONTHLY_SPEND_CAP_USD_MICROS",
  "MEM0_PROVIDER_SPEND_LIMIT_CONFIRMED",
  "OCR_ENABLED",
  "SANDBOX_ENABLED",
  "RESEARCH_PLAN_EXECUTION_ENABLED",
  "RESEARCH_SYNTHESIS_ENABLED",
  "PUBLIC_PAPER_EVIDENCE_ENABLED",
  "NOTIFICATIONS_EMAIL_ENABLED",
  "RESEND_API_KEY",
  "NOTIFICATIONS_FROM_EMAIL",
  "RESEND_WEBHOOK_SECRET",
  "NOTIFICATIONS_UNSUBSCRIBE_SECRET",
  "NOTIFICATIONS_UNSUBSCRIBE_SECRET_PREVIOUS",
  "LANGFUSE_PUBLIC_KEY",
  "LANGFUSE_SECRET_KEY",
  "LANGFUSE_HOST",
  "SENTRY_DSN",
  "SENTRY_TRACES_SAMPLE_RATE",
] as const satisfies readonly (keyof Cloudflare.Env)[];

type ForwardedSecretKey = (typeof SECRET_TO_BACKEND_KEYS)[number];
type ForwardedSecrets = Pick<Cloudflare.Env, ForwardedSecretKey>;

/** Keep container startup configuration explicit, typed, and free of secrets in source. */
export function buildBackendEnvironment(
  bindings: ForwardedSecrets,
): Record<string, string> {
  const result: Record<string, string> = {
    APP_ENV: "production",
    LANGGRAPH_STRICT_MSGPACK: "true",
  };

  for (const key of SECRET_TO_BACKEND_KEYS) {
    const value = bindings[key];
    if (typeof value === "string") {
      result[key] = value;
    }
  }

  return result;
}

/** Re-target the URL without reading, buffering, or changing an SSE body. */
export function requestForBackend(request: Request): Request {
  const url = new URL(request.url);
  url.protocol = "http:";
  url.host = "container";

  const forwarded = new Request(url, request);
  forwarded.headers.delete("host");
  return forwarded;
}

/** Return the Container Fetcher's original Response to preserve SSE streaming. */
export function forwardToBackend(port: Fetcher, request: Request): Promise<Response> {
  return port.fetch(requestForBackend(request));
}
