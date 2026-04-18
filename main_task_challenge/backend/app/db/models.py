from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RunStatus(str, enum.Enum):
    CREATED = "created"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status"),
        default=RunStatus.CREATED,
        nullable=False,
    )
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    log_path: Mapped[str] = mapped_column(String(512), nullable=False)
    ground_truth_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    start_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="PAD_IDLE")
    end_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="LANDED")
    fallback_end_stage: Mapped[str | None] = mapped_column(String(32), nullable=True, default="DESCENT")
    result_csv_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    point_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    endpoint_error_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    rms_crosstrack_error_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_time_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    wall_time_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    points_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
