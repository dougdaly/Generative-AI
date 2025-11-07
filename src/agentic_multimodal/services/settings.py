# services/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,          # We'll pass the path from the registry
        extra="ignore",         # Ignore unknown keys in .env
        case_sensitive=False,
    )

    # Observability / LangSmith
    LANGCHAIN_TRACING_V2: bool = Field(default=True)
    LANGSMITH_TRACING: bool = Field(default=True)
    LANGSMITH_PROJECT: str = Field(default="langgraph_langsmith_demo")
    LANGSMITH_API_KEY: str | None = None  # asserted only if tracing is on

    # Providers (optional unless you actually use them)
    OPENAI_API_KEY: str | None = None
    HUGGINGFACE_HUB_TOKEN: str | None = None

    # Output locations (strings so .env is easy; we’ll coerce to Path later)
    RESULTS_DIR: str | None = None
    CACHE_DIR: str | None = None

    # Knobs
    RATE_LIMIT_PER_SEC: float = Field(default=2.0)
    TIMEOUT_SECS: float = Field(default=60.0)
