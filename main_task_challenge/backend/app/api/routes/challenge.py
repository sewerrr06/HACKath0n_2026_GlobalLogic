from __future__ import annotations

import csv
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psutil
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models import Run, RunStatus
from app.schemas.run import RunRead
from app.worker.celery_app import celery_app
from app.worker.tasks import process_run_task

router = APIRouter()


def _store_upload(file: UploadFile, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    return destination


def _read_trajectory_points(csv_path: Path, limit: int) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if index >= limit:
                break
            points.append(
                {
                    "timestamp": float(row["timestamp"]),
                    "x": float(row["x"]),
                    "y": float(row["y"]),
                    "z": float(row["z"]),
                }
            )
    return points


@router.post("/upload", response_model=RunRead, status_code=status.HTTP_201_CREATED)
def upload_data(
    name: str = Form(...),
    log_file: UploadFile = File(...),
    ground_truth_file: UploadFile | None = File(default=None),
    start_stage: str = Form(default="PAD_IDLE"),
    end_stage: str = Form(default="LANDED"),
    fallback_end_stage: str | None = Form(default="DESCENT"),
    enqueue: bool = Form(default=True),
    db: Session = Depends(get_db),
) -> Run:
    settings = get_settings()

    upload_id = str(uuid.uuid4())
    upload_dir = settings.uploads_dir / upload_id
    log_filename = Path(log_file.filename or "input.bin").name
    log_path = _store_upload(log_file, upload_dir / log_filename)

    ground_truth_path: Path | None = None
    if ground_truth_file is not None and ground_truth_file.filename:
        ground_truth_name = Path(ground_truth_file.filename).name
        ground_truth_path = _store_upload(ground_truth_file, upload_dir / ground_truth_name)

    run = Run(
        name=name,
        log_path=str(log_path),
        ground_truth_path=str(ground_truth_path) if ground_truth_path else None,
        start_stage=start_stage,
        end_stage=end_stage,
        fallback_end_stage=fallback_end_stage,
        status=RunStatus.CREATED,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if enqueue:
        task = process_run_task.delay(run.id)
        run.status = RunStatus.QUEUED
        run.task_id = task.id
        run.queued_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)

    return run


@router.get("/trajectory")
def get_trajectory(
    run_id: str = Query(...),
    limit: int = Query(default=50000, ge=1, le=500000),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if not run.result_csv_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trajectory is not generated yet",
        )

    csv_path = Path(run.result_csv_path)
    if not csv_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trajectory file is missing on disk",
        )

    points = _read_trajectory_points(csv_path, limit=limit)
    return {
        "run_id": run.id,
        "status": run.status,
        "returned_points": len(points),
        "point_count": run.point_count,
        "points": points,
    }


@router.get("/metrics")
def get_metrics(run_id: str = Query(...), db: Session = Depends(get_db)) -> dict[str, object]:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {
        "run_id": run.id,
        "status": run.status,
        "point_count": run.point_count,
        "endpoint_error_m": run.endpoint_error_m,
        "rms_crosstrack_error_m": run.rms_crosstrack_error_m,
    }


@router.get("/status")
def get_status(
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    system_stats = {
        "cpu_percent": psutil.cpu_percent(interval=0.05),
        "memory_percent": psutil.virtual_memory().percent,
    }

    if run_id is None:
        return {"system": system_stats}

    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    task_state = None
    if run.task_id:
        task_result = AsyncResult(run.task_id, app=celery_app)
        task_state = task_result.state

    return {
        "run_id": run.id,
        "status": run.status,
        "task_id": run.task_id,
        "task_state": task_state,
        "queued_at": run.queued_at,
        "started_at": run.started_at,
        "processed_at": run.processed_at,
        "system": system_stats,
    }


@router.get("/benchmark")
def get_benchmark(run_id: str = Query(...), db: Session = Depends(get_db)) -> dict[str, object]:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return {
        "run_id": run.id,
        "status": run.status,
        "cpu_time_sec": run.cpu_time_sec,
        "wall_time_sec": run.wall_time_sec,
        "points_per_sec": run.points_per_sec,
        "point_count": run.point_count,
    }
