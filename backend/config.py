from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openrouter_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    mistral_api_key: str = ""

    firecrawl_api_key: str = ""
    semantic_scholar_api_key: str = ""

    mem0_api_key: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    database_url: str = ""

    app_url: str = "http://localhost:3000"
    cors_origins: str = ""
    next_public_api_url: str = "http://localhost:8000"
    redis_url: str = ""

    admin_api_key: str = ""

    max_summaries_per_run: int = 20
    max_searches_per_day_per_user: int = 100
    ocr_enabled: bool = False
    sandbox_enabled: bool = False
    research_plan_execution_enabled: bool = False
    research_synthesis_enabled: bool = False

    notifications_email_enabled: bool = False
    resend_api_key: str = ""
    notifications_from_email: str = ""
    resend_webhook_secret: str = ""
    notifications_unsubscribe_secret: str = ""
    notifications_unsubscribe_secret_previous: str = ""

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    app_env: str = "development"

def get_settings() -> Settings:
    return Settings()
