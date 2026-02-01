"""Celery app shared by the API (producer) and the worker (consumer).

Kept dependency-light: the Vercel serverless function imports this to enqueue
jobs by task NAME (send_task) — the heavy pipeline code is only imported inside
the worker process.
"""
from __future__ import annotations

from celery import Celery

import config


def _with_ssl_params(url: str) -> str:
    """Upstash uses rediss:// — Celery requires an explicit ssl_cert_reqs param."""
    if url.startswith("rediss://") and "ssl_cert_reqs" not in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}ssl_cert_reqs=required"
    return url


BROKER_URL = _with_ssl_params(config.REDIS_URL)

celery_app = Celery("data_analyst", broker=BROKER_URL, backend=BROKER_URL)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=1800,       # hard kill: 30 min per report
    task_soft_time_limit=1500,
)

TASK_RUN_ANALYSIS = "run_analysis"
