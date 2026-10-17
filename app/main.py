"""FastAPI application: accepts uploads, enqueues analysis, reports job status."""

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Job, JobStatus
from app.schemas import JobCreated, JobStatusResponse
from app.security import require_api_key
from app.tasks import analyze_video_task

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".mp4", ".mov"}
CHUNK_SIZE = 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="Video Violation Analyzer",
    version="1.0.0",
    lifespan=lifespan,
    dependencies=[Depends(require_api_key)],
)


def _save_upload(upload: UploadFile, destination: Path) -> int:
    """Copy the upload to disk in chunks, enforcing the size limit. Returns bytes written."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with destination.open("wb") as out:
            while chunk := upload.file.read(CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds {settings.max_upload_mb} MB limit",
                    )
                out.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return written


# Sync handlers run in FastAPI's threadpool, so disk, DB and broker I/O
# do not block the event loop.
@app.post("/v1/analyze", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreated)
def analyze(file: UploadFile = File(...)) -> JobCreated:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .mp4 and .mov files are accepted",
        )

    job_id = str(uuid.uuid4())
    destination = settings.upload_dir / f"{job_id}{extension}"
    if _save_upload(file, destination) == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    with SessionLocal() as db:
        db.add(Job(id=job_id, status=JobStatus.PROCESSING.value, original_filename=file.filename))
        db.commit()

    try:
        analyze_video_task.delay(job_id, str(destination))
    except Exception as exc:
        logger.exception("Failed to enqueue job %s", job_id)
        destination.unlink(missing_ok=True)
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status = JobStatus.FAILED.value
            job.error = f"Could not enqueue analysis task: {exc}"
            db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Task queue unavailable") from exc

    return JobCreated(job_id=job_id)


@app.get("/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobStatusResponse(job_id=job.id, status=job.status, result=job.result, error=job.error)
