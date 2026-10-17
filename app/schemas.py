"""Pydantic schemas for API responses and the analysis result."""

from typing import Literal

from pydantic import BaseModel


class Event(BaseModel):
    event_sec: float
    start_sec: float
    end_sec: float
    timestamp: str
    type_key: str
    name_ru: str
    name_en: str
    rule_ref: str
    desc_ru: str
    desc_en: str


class AnalysisResult(BaseModel):
    violation: bool
    duration_sec: float
    events: list[Event]


class JobCreated(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["processing", "done", "failed"]
    result: AnalysisResult | None = None
    error: str | None = None
