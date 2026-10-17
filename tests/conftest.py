import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

# Must be set before any `app` module is imported: settings are read at import time.
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="video-analyzer-test-")
os.environ["DATA_DIR"] = _TEST_DATA_DIR
os.environ["API_KEY"] = "test-key"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

API_KEY = "test-key"
FPS = 10
WIDTH, HEIGHT = 320, 240


def write_video(path: Path, moving_sec: float, still_sec: float) -> Path:
    """A white square moves across a dark background, then the frame stays static."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))
    assert writer.isOpened(), "OpenCV could not open a VideoWriter for mp4v"
    x = 0
    for _ in range(int(moving_sec * FPS)):
        frame = np.full((HEIGHT, WIDTH, 3), 30, dtype=np.uint8)
        cv2.rectangle(frame, (x, 80), (x + 60, 140), (255, 255, 255), -1)
        writer.write(frame)
        x = (x + 12) % (WIDTH - 60)
    still = np.full((HEIGHT, WIDTH, 3), 30, dtype=np.uint8)
    for _ in range(int(still_sec * FPS)):
        writer.write(still)
    writer.release()
    return path


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth():
    return {"X-API-Key": API_KEY}
