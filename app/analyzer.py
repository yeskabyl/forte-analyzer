"""Video analysis with OpenCV.

This is a baseline heuristic, not a trained model. It samples frames, measures
how much of the picture changes between samples (frame differencing), and flags
a "leave_unlocked_workstation" event when a burst of motion is followed by a
long stretch of stillness: the pattern of someone getting up and walking out
of a fixed desk camera's view. It cannot tell whether the PC was actually
locked; that needs screen/person detection and is the next step for a real model.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.config import settings
from app.schemas import AnalysisResult, Event

ANALYSIS_WIDTH = 160

VIOLATION_CATALOG: dict[str, dict[str, str]] = {
    "leave_unlocked_workstation": {
        "name_ru": "Уход с рабочего места без блокировки ПК",
        "name_en": "Leaving workstation unlocked",
        "rule_ref": "Постановление Правления НБРК № 48",
        "desc_ru": "Сотрудник покидает рабочее место.",
        "desc_en": "The employee leaves the desk.",
    },
}


class VideoReadError(Exception):
    """The file could not be decoded as a video."""


@dataclass(frozen=True)
class AnalyzerConfig:
    sample_fps: float
    pixel_diff_threshold: int
    motion_threshold: float
    min_active_sec: float
    min_still_sec: float
    event_pre_sec: float
    event_post_sec: float

    @classmethod
    def from_settings(cls) -> "AnalyzerConfig":
        return cls(
            sample_fps=settings.sample_fps,
            pixel_diff_threshold=settings.pixel_diff_threshold,
            motion_threshold=settings.motion_threshold,
            min_active_sec=settings.min_active_sec,
            min_still_sec=settings.min_still_sec,
            event_pre_sec=settings.event_pre_sec,
            event_post_sec=settings.event_post_sec,
        )


def format_timestamp(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def _prepare_frame(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    if width > ANALYSIS_WIDTH:
        new_height = max(1, round(height * ANALYSIS_WIDTH / width))
        frame = cv2.resize(frame, (ANALYSIS_WIDTH, new_height), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def _motion_score(prev: np.ndarray, curr: np.ndarray, pixel_diff_threshold: int) -> float:
    """Fraction of pixels whose brightness changed by more than the threshold."""
    diff = cv2.absdiff(prev, curr)
    return float(np.count_nonzero(diff > pixel_diff_threshold)) / diff.size


def _sample_motion(path: Path, cfg: AnalyzerConfig) -> tuple[float, int, int, list[float], list[float]]:
    """Return (fps, metadata_frame_count, decoded_frame_count, sample_times, motion_scores)."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoReadError("OpenCV could not open the video file")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or math.isnan(fps) or fps <= 0:
            raise VideoReadError("Video reports an invalid FPS value")
        meta_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        step = max(1, round(fps / cfg.sample_fps))

        times: list[float] = []
        scores: list[float] = []
        prev: np.ndarray | None = None
        index = 0
        # grab() decodes without converting to BGR, so skipped frames are cheap.
        while cap.grab():
            if index % step == 0:
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    curr = _prepare_frame(frame)
                    if prev is not None and prev.shape == curr.shape:
                        times.append(index / fps)
                        scores.append(_motion_score(prev, curr, cfg.pixel_diff_threshold))
                    prev = curr
            index += 1
    finally:
        cap.release()

    if index == 0:
        raise VideoReadError("Video contains no decodable frames")
    return fps, meta_frame_count, index, times, scores


def _find_departures(times: list[float], scores: list[float], duration: float, cfg: AnalyzerConfig) -> list[float]:
    """Times at which a motion burst ends and is followed by sustained stillness."""
    sample_period = 1.0 / cfg.sample_fps
    active = [score >= cfg.motion_threshold for score in scores]
    departures: list[float] = []
    n = len(scores)
    i = 0
    while i < n:
        if not active[i]:
            i += 1
            continue
        burst_start = i
        while i < n and active[i]:
            i += 1
        burst_end = i - 1
        burst_len = times[burst_end] - times[burst_start] + sample_period
        if burst_len < cfg.min_active_sec:
            continue
        while i < n and not active[i]:
            i += 1
        # Stillness lasts until the next motion sample, or to the end of the video.
        still_until = times[i] if i < n else duration
        if still_until - times[burst_end] >= cfg.min_still_sec:
            departures.append(times[burst_end])
    return departures


def analyze_video(path: str | Path, cfg: AnalyzerConfig | None = None) -> AnalysisResult:
    cfg = cfg or AnalyzerConfig.from_settings()
    fps, meta_frame_count, decoded_frames, times, scores = _sample_motion(Path(path), cfg)

    # Container metadata is authoritative; some .mov files report 0 frames, so
    # fall back to the number of frames actually decoded.
    frame_count = meta_frame_count if meta_frame_count > 0 else decoded_frames
    duration = frame_count / fps

    catalog_entry = VIOLATION_CATALOG["leave_unlocked_workstation"]
    events = [
        Event(
            event_sec=round(t, 1),
            start_sec=round(max(0.0, t - cfg.event_pre_sec), 1),
            end_sec=round(min(duration, t + cfg.event_post_sec), 1),
            timestamp=format_timestamp(t),
            type_key="leave_unlocked_workstation",
            **catalog_entry,
        )
        for t in _find_departures(times, scores, duration, cfg)
    ]
    return AnalysisResult(violation=bool(events), duration_sec=round(duration, 1), events=events)
