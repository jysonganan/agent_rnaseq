"""ARQ worker entry point (``python -m arq src.worker.WorkerSettings``).

Registers both jobs: chat intent parsing (LLM) and pipeline execution (deterministic).
"""

from __future__ import annotations

from arq.connections import RedisSettings

from src.api.background.runner import run_pipeline
from src.config import get_settings
from src.workers.tasks import process_chat_message


class WorkerSettings:
    functions = [process_chat_message, run_pipeline]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # Pipeline runs can take hours (STAR, GATK, CellRanger).
    job_timeout = 24 * 60 * 60
