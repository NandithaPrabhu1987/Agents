from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # AI / Model
    ai_provider: str = "groq"  # env: AI_PROVIDER
    groq_model: str = "llama-3.1-8b-instant"  # env: GROQ_MODEL
    groq_api_key: Optional[str] = None  # env: GROQ_API_KEY

    # Logging
    log_level: str = "INFO"  # env: LOG_LEVEL

    # Config
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
