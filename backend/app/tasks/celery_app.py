from __future__ import annotations

from urllib.parse import quote_plus

from celery import Celery

from ..core.settings import settings


def _build_redis_url() -> str:
    if settings.CELERY_BROKER_URL:
        return settings.CELERY_BROKER_URL
    if not (settings.AZURE_REDIS_HOST and settings.AZURE_REDIS_KEY):
        raise RuntimeError("Redis settings are required for Celery broker/result backend.")
    password = quote_plus(settings.AZURE_REDIS_KEY)
    return f"rediss://:{password}@{settings.AZURE_REDIS_HOST}:{settings.REDIS_SSL_PORT}/0"


broker_url = _build_redis_url()
result_backend = settings.CELERY_RESULT_BACKEND or broker_url

celery_app = Celery(
    "theogen",
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks.theory_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    imports=("app.tasks.theory_tasks",),
)
