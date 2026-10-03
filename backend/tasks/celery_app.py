"""Celery application — background jobs for delayed payment recovery."""

from celery import Celery

from config import get_settings

settings = get_settings()

celery_app = Celery(
    "revive_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["tasks.retry_scheduler"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    # So countdown jobs survive short worker restarts in demo
    broker_connection_retry_on_startup=True,
)
