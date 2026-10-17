import uuid

from app.analyzer import analyze_video, format_timestamp
from app.config import settings
from tests.conftest import write_video


def _upload(client, auth, path, filename=None):
    with path.open("rb") as fh:
        return client.post(
            "/v1/analyze",
            headers=auth,
            files={"file": (filename or path.name, fh, "video/mp4")},
        )


def test_missing_api_key_returns_401(client):
    assert client.get(f"/v1/jobs/{uuid.uuid4()}").status_code == 401
    assert client.post("/v1/analyze").status_code == 401


def test_wrong_api_key_returns_401(client):
    response = client.get(f"/v1/jobs/{uuid.uuid4()}", headers={"X-API-Key": "nope"})
    assert response.status_code == 401


def test_unknown_job_returns_404(client, auth):
    assert client.get(f"/v1/jobs/{uuid.uuid4()}", headers=auth).status_code == 404


def test_rejects_unsupported_extension(client, auth, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not a video")
    assert _upload(client, auth, path).status_code == 415


def test_departure_is_reported_as_violation(client, auth, tmp_path):
    video = write_video(tmp_path / "departure.mp4", moving_sec=4, still_sec=6)

    response = _upload(client, auth, video)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert str(uuid.UUID(job_id)) == job_id

    # Celery runs eagerly in tests, so the job is already finished.
    body = client.get(f"/v1/jobs/{job_id}", headers=auth).json()
    assert body["status"] == "done", body
    assert body["error"] is None
    result = body["result"]
    assert result["violation"] is True
    assert result["duration_sec"] == 10.0
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert 3.0 <= event["event_sec"] <= 4.0
    assert event["start_sec"] <= event["event_sec"] <= event["end_sec"] <= result["duration_sec"]
    assert event["type_key"] == "leave_unlocked_workstation"
    assert event["timestamp"] == format_timestamp(event["event_sec"])
    assert event["rule_ref"] == "Постановление Правления НБРК № 48"

    assert list(settings.upload_dir.iterdir()) == [], "temporary video must be deleted"


def test_static_video_has_no_violation(tmp_path):
    video = write_video(tmp_path / "static.mp4", moving_sec=0, still_sec=5)
    result = analyze_video(video)
    assert result.violation is False
    assert result.events == []
    assert result.duration_sec == 5.0


def test_corrupt_file_marks_job_failed(client, auth, tmp_path):
    path = tmp_path / "broken.mov"
    path.write_bytes(b"\x00" * 4096)

    response = _upload(client, auth, path)
    assert response.status_code == 202
    body = client.get(f"/v1/jobs/{response.json()['job_id']}", headers=auth).json()
    assert body["status"] == "failed"
    assert body["result"] is None
    assert "VideoReadError" in body["error"]
    assert list(settings.upload_dir.iterdir()) == []


def test_api_prefix_alias(client, auth, tmp_path):
    video = write_video(tmp_path / "alias.mov", moving_sec=0, still_sec=3)
    with video.open("rb") as fh:
        response = client.post("/api/v1/analyze", headers=auth, files={"file": ("alias.mov", fh, "video/quicktime")})
    assert response.status_code == 202
    body = client.get(f"/api/v1/jobs/{response.json()['job_id']}", headers=auth).json()
    assert body["status"] == "done"
    assert body["result"]["violation"] is False


def test_cors_preflight_needs_no_api_key(client):
    response = client.options(
        "/api/v1/analyze",
        headers={
            "Origin": "http://localhost:5500",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_401_is_readable_cross_origin(client):
    response = client.get(f"/api/v1/jobs/{uuid.uuid4()}", headers={"Origin": "http://localhost:5500"})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "*"


def test_timestamp_format():
    assert format_timestamp(22.0) == "00:22"
    assert format_timestamp(125.4) == "02:05"
