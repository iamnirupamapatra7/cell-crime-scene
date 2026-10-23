from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Gemini. Leave the key empty to run with the offline heuristic planner.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-4-argon"
    gemini_thinking_level: str = "high"
    gemini_timeout_s: float = 120

    # MongoDB Atlas. Leave empty to use the local JSON store.
    mongodb_uri: str = ""
    mongodb_db: str = "cell_crime_scene"
    atlas_search_index: str = "ccs_search"
    atlas_vector_index: str = "ccs_vector"

    storage_dir: Path = ROOT / "storage"
    sample_dir: Path = ROOT / "sample_cases"
    max_attempts: int = 4
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
