"""Celery tasks."""

import logging
from pathlib import Path

from app.analyzer import analyze_video
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, JobStatus

logger = logging.getLogger(__name__)


def _finish_job(job_id: str, status: JobStatus, result: dict | None = None, error: str | None = None) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            logger.error("Job %s not found in the database", job_id)
            return
        job.status = status.value
        job.result = result
        job.error = error
        db.commit()


@celery_app.task(name="analyze_video")
def analyze_video_task(job_id: str, file_path: str) -> None:
    logger.info("Analyzing job %s (%s)", job_id, file_path)
    try:
        result = analyze_video(file_path)
        _finish_job(job_id, JobStatus.DONE, result=result.model_dump())
        logger.info("Job %s done: violation=%s, events=%d", job_id, result.violation, len(result.events))
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        _finish_job(job_id, JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
    finally:
        Path(file_path).unlink(missing_ok=True)
