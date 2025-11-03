# src/agentic_multimodal/services/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    WIKIDATA_ENDPOINT: str = "https://query.wikidata.org/sparql"
    SDXL_MODEL_ID: str = "stabilityai/sdxl-turbo"  # adjust to your stack
    CONCURRENCY: int = 6
    class Config:
        env_file = ".env"

