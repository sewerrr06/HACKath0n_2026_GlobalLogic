from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import RunStatus


class RunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    log_path: str = Field(min_length=1, max_length=512)
    ground_truth_path: str | None = Field(default=None, max_length=512)
    start_stage: str = Field(default="PAD_IDLE", max_length=32)
    end_stage: str = Field(default="LANDED", max_length=32)
    fallback_end_stage: str | None = Field(default="DESCENT", max_length=32)


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: RunStatus
    task_id: str | None
    log_path: str
    ground_truth_path: str | None
    start_stage: str
    end_stage: str
    fallback_end_stage: str | None
    result_csv_path: str | None
    point_count: int | None
    endpoint_error_m: float | None
    rms_crosstrack_error_m: float | None
    cpu_time_sec: float | None
    wall_time_sec: float | None
    points_per_sec: float | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    processed_at: datetime | None
