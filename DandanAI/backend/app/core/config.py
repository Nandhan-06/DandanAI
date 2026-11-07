"""Central configuration. All external links/credentials come from environment variables (.env)."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _clean_val(v: any) -> any:
    if not isinstance(v, str):
        return v
    s = v.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    if "#" in s:
        s = s.split("#")[0].strip()
    return s


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def strip_inline_comments(cls, data: any) -> any:
        if isinstance(data, dict):
            return {k: _clean_val(v) for k, v in data.items()}
        return data

    app_env: str = "development"  # development | test | production
    # ---- Neon (the ONLY supported application database) ----
    database_provider: str = "neon"
    database_url: str = ""  # Neon POOLED connection string (normal traffic)
    direct_url: str = ""  # Neon DIRECT connection string (Alembic migrations)
    # Test-only escape hatch. Honoured ONLY when APP_ENV=test. Never a production fallback.
    allow_ephemeral_test_db: bool = False

    jwt_secret_key: str = "change-me-in-env-at-least-32-chars-long"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_name: str = "Platform Admin"
    cors_origins: str = "http://localhost:3000"

    # ---- storage (private object storage; metadata lives in Neon) ----
    storage_provider: str = "local"  # local | s3
    storage_dir: str = "./storage"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    max_upload_mb: int = 15

    # ---- AI providers (mock needs no credentials) ----
    llm_provider: str = "mock"  # mock | openai | gemini
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""  # optional OpenAI-compatible base URL
    embedding_provider: str = "mock"  # mock | openai | gemini
    embedding_model: str = ""
    embedding_api_key: str = ""
    embedding_dim: int = 256  # pgvector column dimension; changing it needs a new migration
    ocr_provider: str = "auto"  # auto | tesseract | mock | none
    stt_provider: str = "mock"
    stt_api_key: str = ""
    tts_provider: str = "edge-tts"  # edge-tts | mock | openai
    tts_api_key: str = ""
    tts_voice: str = "en-CA-LiamNeural"  # Liam (Canada) male voice; fallback to UK/US male voices
    avatar_provider: str = "mock"
    avatar_api_key: str = ""
    reranker_provider: str = "lexical"

    # ---- observability (optional) ----
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    seed_synthetic_corpus: bool = True
    allow_external_fetch: bool = False  # legal-source monitors never hit the network unless true

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
