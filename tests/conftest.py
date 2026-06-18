import os

import pytest

# Set required env vars before any module imports that call get_settings()
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("API_KEY_BOOTSTRAP", "test-bootstrap-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    """Reset the lru_cache on Settings so each test gets a fresh instance."""
    from src.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
