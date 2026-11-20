declare namespace Cloudflare {
  interface Env {
    ZENITH_BACKEND: DurableObjectNamespace<
      import("./index").ZenithBackendContainer
    >;

    // Add these as Worker secrets (or local .dev.vars entries). Never commit
    // values. They are copied into the backend Container only at startup.
    APP_URL: string;
    CORS_ORIGINS?: string;
    OPENROUTER_API_KEY?: string;
    OPENAI_API_KEY?: string;
    ANTHROPIC_API_KEY?: string;
    GOOGLE_API_KEY?: string;
    MISTRAL_API_KEY?: string;
    SEMANTIC_SCHOLAR_API_KEY?: string;
    GITHUB_TOKEN?: string;
    MEM0_API_KEY?: string;
    SUPABASE_URL: string;
    SUPABASE_ANON_KEY?: string;
    SUPABASE_SERVICE_ROLE_KEY: string;
    SUPABASE_JWT_SECRET?: string;
    REDIS_URL: string;
    DATABASE_URL: string;
    ADMIN_API_KEY?: string;
    MAX_SUMMARIES_PER_RUN?: string;
    MAX_SEARCHES_PER_DAY_PER_USER?: string;
    LLM_ENABLED?: string;
    LLM_DAILY_SPEND_CAP_USD_MICROS?: string;
    LLM_MONTHLY_SPEND_CAP_USD_MICROS?: string;
    MEM0_PROVIDER_SPEND_LIMIT_CONFIRMED?: string;
    OCR_ENABLED?: string;
    SANDBOX_ENABLED?: string;
    RESEARCH_PLAN_EXECUTION_ENABLED?: string;
    RESEARCH_SYNTHESIS_ENABLED?: string;
    PUBLIC_PAPER_EVIDENCE_ENABLED?: string;
    NOTIFICATIONS_EMAIL_ENABLED?: string;
    RESEND_API_KEY?: string;
    NOTIFICATIONS_FROM_EMAIL?: string;
    RESEND_WEBHOOK_SECRET?: string;
    NOTIFICATIONS_UNSUBSCRIBE_SECRET?: string;
    NOTIFICATIONS_UNSUBSCRIBE_SECRET_PREVIOUS?: string;
    LANGFUSE_PUBLIC_KEY?: string;
    LANGFUSE_SECRET_KEY?: string;
    LANGFUSE_HOST?: string;
    SENTRY_DSN?: string;
    SENTRY_TRACES_SAMPLE_RATE?: string;
  }
}
