from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./agent_rnaseq.db"

    # ── API auth ──────────────────────────────────────────────────────────────
    api_key_bootstrap: str = Field(..., description="Bootstrap admin API key")

    # ── LLM ──────────────────────────────────────────────────────────────────
    openai_api_key: str = Field(..., description="OpenAI API key for Agents SDK")

    # ── Output storage ────────────────────────────────────────────────────────
    output_root: str = "/tmp/agent_rnaseq"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── AWS (all optional) ────────────────────────────────────────────────────
    aws_default_region: str = "us-east-1"
    s3_artifact_bucket: str = ""
    aws_batch_job_queue: str = ""
    aws_batch_job_definition: str = ""

    @model_validator(mode="after")
    def _validate_production_requirements(self) -> "Settings":
        if self.app_env == "production":
            if not self.s3_artifact_bucket:
                raise ValueError("S3_ARTIFACT_BUCKET is required in production")
            if not self.aws_batch_job_queue:
                raise ValueError("AWS_BATCH_JOB_QUEUE is required in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
