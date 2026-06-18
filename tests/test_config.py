import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_loads_with_required_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    # Clear env vars set by conftest so defaults are exercised
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="sk-test",
        api_key_bootstrap="bootstrap-key",
    )
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.database_url == "sqlite:///./agent_rnaseq.db"
    assert settings.output_root == "/tmp/agent_rnaseq"
    assert settings.aws_default_region == "us-east-1"


def test_settings_raises_on_missing_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            api_key_bootstrap="bootstrap-key",
        )


def test_settings_raises_on_missing_bootstrap_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_KEY_BOOTSTRAP", raising=False)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            openai_api_key="sk-test",
        )


def test_production_requires_s3_bucket() -> None:
    with pytest.raises(ValidationError, match="S3_ARTIFACT_BUCKET"):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            openai_api_key="sk-test",
            api_key_bootstrap="bootstrap-key",
            app_env="production",
        )


def test_production_requires_batch_queue() -> None:
    with pytest.raises(ValidationError, match="AWS_BATCH_JOB_QUEUE"):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            openai_api_key="sk-test",
            api_key_bootstrap="bootstrap-key",
            app_env="production",
            s3_artifact_bucket="my-bucket",
        )


def test_production_passes_with_all_required() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="sk-test",
        api_key_bootstrap="bootstrap-key",
        app_env="production",
        s3_artifact_bucket="my-bucket",
        aws_batch_job_queue="arn:aws:batch:us-east-1:123456789012:job-queue/q",
    )
    assert settings.app_env == "production"
    assert settings.s3_artifact_bucket == "my-bucket"
