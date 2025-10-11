from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache
from pathlib import Path
from typing import Optional

class Settings(BaseSettings):
    # AI / Model
    ai_provider: str = "rule"  # env: AI_PROVIDER
    groq_model: str = "llama-3.1-8b-instant"  # env: GROQ_MODEL
    groq_api_key: Optional[str] = None  # env: GROQ_API_KEY

    # Observability: Langfuse
    langfuse_host: Optional[str] = None  # env: LANGFUSE_HOST
    langfuse_public_key: Optional[str] = None  # env: LANGFUSE_PUBLIC_KEY
    langfuse_secret_key: Optional[str] = None  # env: LANGFUSE_SECRET_KEY

    # Chat / Memory
    max_history_messages: int = 12  # env: MAX_HISTORY_MESSAGES

    # Planning defaults
    default_plan_cap: int = 100  # env: DEFAULT_PLAN_CAP
    max_auto_steps: int = 5  # env: MAX_AUTO_STEPS

    # Phase 4 Memory
    memory_dir: Path = Path("logs/memory")  # env: MEMORY_DIR
    memory_max_items: int = 300  # env: MEMORY_MAX_ITEMS

    # Phase 5 Memory Enhancements
    memory_relevance_limit: int = 5  # env: MEMORY_RELEVANCE_LIMIT
    memory_max_prompt_chars: int = 1200  # env: MEMORY_MAX_PROMPT_CHARS
    memory_half_life_hours: float = 48.0  # env: MEMORY_HALF_LIFE_HOURS
    min_core_tools_before_final: int = 2  # env: MIN_CORE_TOOLS_BEFORE_FINAL

    # Token limits (Phase 5+)
    planner_max_tokens: int = 200  # env: PLANNER_MAX_TOKENS
    judge_max_tokens: int = 150    # env: JUDGE_MAX_TOKENS

    # Auditing
    audit_base: Path = Path("logs/audit")  # env: AUDIT_BASE
    truncate_audit_chars: int = 2000  # env: TRUNCATE_AUDIT_CHARS

    # Logging
    log_level: str = "INFO"  # env: LOG_LEVEL

    # Config
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
