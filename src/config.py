"""Application configuration, loaded from environment variables / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict

_instance: BaseSettings | None = None

class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    # --- App ---
    app_port: int
    app_host: str
    app_log_level: str
    papers_dir: str = "resource/papers"

    # --- Postgres ---
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host_port: int
    postgres_dashboard_port: int
    database_url: str

    # --- Redis ---
    redis_host_port: int
    redis_dashboard_port: int
    redis_url: str

    # --- LLM providers ---
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_url: str | None = None
    ollama_api_key: str | None = None
    ollama_num_predict: int = 2048
    ollama_keep_alive: str = "10m"
    other_llm_provider_url: str | None = None
    other_llm_provider_api_key: str | None = None


def initialize_global_config() -> Config:
    """Initialize the global configuration instance."""
    global _instance
    if _instance is None:
        _instance = Config()
    return _instance    


def get_global_config() -> Config:
    """Get the global configuration instance."""
    if _instance is None:
        raise RuntimeError("Config has not been initialized. Call initialize_config() first.")
    return _instance