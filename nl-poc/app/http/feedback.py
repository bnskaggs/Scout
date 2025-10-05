"""Feedback endpoint for telemetry loop."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator

from app.telemetry import events

router = APIRouter()


class FeedbackRequest(BaseModel):
    request_id: str
    helpful: bool
    corrected_text: str | None = None

    @validator("request_id")
    def _validate_request_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("request_id is required")
        return value.strip()

    @validator("corrected_text", pre=True)
    def _normalize_corrected_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


@router.post("/feedback")
def submit_feedback(payload: FeedbackRequest) -> dict:
    request_id = payload.request_id
    if not events.request_seen_recently(request_id):
        raise HTTPException(status_code=404, detail="request_id not found in the last 24h")
    if events.feedback_rate_limited(request_id):
        raise HTTPException(status_code=429, detail="Feedback already submitted recently")
    events.log_feedback(request_id, payload.helpful, payload.corrected_text)
    return {"status": "ok"}
