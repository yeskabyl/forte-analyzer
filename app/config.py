"""Application settings, read once from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_key: str
    data_dir: Path
    upload_dir: Path
    database_url: str
    redis_url: str
    max_upload_mb: int
    cors_origins: list[str]
    celery_task_always_eager: bool
    # Analyzer tuning
    sample_fps: float
    pixel_diff_threshold: int
    motion_threshold: float
    min_active_sec: float
    min_still_sec: float
    event_pre_sec: float
    event_post_sec: float


def load_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    upload_dir = Path(os.getenv("UPLOAD_DIR", str(data_dir / "uploads"))).resolve()
    database_url = os.getenv("DATABASE_URL", f"sqlite:///{(data_dir / 'jobs.db').as_posix()}")
    return Settings(
        api_key=os.getenv("API_KEY", "forte-secret-key-2026"),
        data_dir=data_dir,
        upload_dir=upload_dir,
        database_url=database_url,
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "500")),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
        celery_task_always_eager=_env_bool("CELERY_TASK_ALWAYS_EAGER", False),
        sample_fps=float(os.getenv("ANALYZER_SAMPLE_FPS", "2")),
        pixel_diff_threshold=int(os.getenv("ANALYZER_PIXEL_DIFF_THRESHOLD", "25")),
        motion_threshold=float(os.getenv("ANALYZER_MOTION_THRESHOLD", "0.02")),
        min_active_sec=float(os.getenv("ANALYZER_MIN_ACTIVE_SEC", "1.0")),
        min_still_sec=float(os.getenv("ANALYZER_MIN_STILL_SEC", "3.0")),
        event_pre_sec=float(os.getenv("ANALYZER_EVENT_PRE_SEC", "2.0")),
        event_post_sec=float(os.getenv("ANALYZER_EVENT_POST_SEC", "3.0")),
    )


settings = load_settings()
