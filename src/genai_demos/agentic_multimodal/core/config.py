from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str | None = None
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.0

    class Config:
        env_prefix = "AMM_"  # e.g., AMM_OPENAI_API_KEY

SRC = Path("../../src/demos/agentic_multimodal").resolve()
CACHE = Path("../../src/demos/agentic_multimodal/cache").resolve()
RESULTS = Path("../../results/agentic_multimodal").resolve()
