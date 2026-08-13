from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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

    app_url: str = "http://localhost:3000"
    next_public_api_url: str = "http://localhost:8000"
    redis_url: str = ""

    admin_api_key: str = ""

    max_summaries_per_run: int = 20

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    app_env: str = "development"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    return Settings()