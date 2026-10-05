from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    database_url: str = "postgresql+asyncpg://revive:revive@localhost:5432/revive_agent"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    # Demo: wait N seconds instead of full timing_offset_minutes (bank cool-down)
    delay_retry_demo_seconds: int = 30
    delay_retry_use_demo_countdown: bool = True

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    # gemini | rules | ollama | openai — use `rules` for zero LLM latency on demos
    llm_provider: str = "rules"
    # Opt-in Gemini drafts. Default off so recovery never waits on a hung LLM.
    llm_draft_enabled: bool = False
    # Hard wall-clock for Gemini; miss → template instantly (no backoff sleep).
    llm_timeout_seconds: float = 2.5

    # Policy guard (deterministic — never LLM-authorized)
    policy_max_retries: int = 3
    policy_quiet_hours_start: int = 22  # IST inclusive
    policy_quiet_hours_end: int = 8  # IST exclusive
    # Comma-separated customer_ids that must never receive recovery outbound
    policy_dnc_customer_ids: str = ""

    app_env: str = "development"
    app_debug: bool = True
    cors_origins: str = "http://localhost:6100,http://localhost:6000,http://localhost:5173,http://localhost:3000"

    @property
    def dnc_customer_id_set(self) -> frozenset[str]:
        return frozenset(x.strip() for x in self.policy_dnc_customer_ids.split(",") if x.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
