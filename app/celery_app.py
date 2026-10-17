"""Celery application. Redis is the broker; job state lives in the SQL database,
so no Celery result backend is configured."""

from celery import Celery
from celery.signals import worker_process_init

from app.config import settings

celery_app = Celery("video_analyzer", broker=settings.redis_url, include=["app.tasks"])

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    # Re-deliver a job if the worker dies mid-analysis instead of losing it.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_always_eager=settings.celery_task_always_eager,
)


@worker_process_init.connect
def _reset_db_pool(**_kwargs):
    # Prefork children must not reuse DB connections inherited from the parent.
    from app.database import engine

    engine.dispose(close=False)
