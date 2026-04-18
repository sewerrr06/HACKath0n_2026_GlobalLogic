from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Run, RunStatus
from app.schemas.run import RunCreate, RunRead
from app.services.run_executor import execute_run
from app.worker.tasks import process_run_task

router = APIRouter()


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
def create_run(payload: RunCreate, db: Session = Depends(get_db)) -> Run:
    run = Run(
        name=payload.name,
        log_path=payload.log_path,
        ground_truth_path=payload.ground_truth_path,
        start_stage=payload.start_stage,
        end_stage=payload.end_stage,
        fallback_end_stage=payload.fallback_end_stage,
        status=RunStatus.CREATED,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=list[RunRead])
def list_runs(
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Run]:
    query = db.query(Run).order_by(Run.created_at.desc()).offset(skip).limit(limit)
    return list(query)


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: str, db: Session = Depends(get_db)) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/{run_id}/process", response_model=RunRead)
def start_processing(
    run_id: str,
    db: Session = Depends(get_db),
    background: bool = Query(default=True),
) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    if run.status in {RunStatus.QUEUED, RunStatus.PROCESSING}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run is already queued or processing",
        )

    if background:
        task = process_run_task.delay(run.id)
        run.status = RunStatus.QUEUED
        run.task_id = task.id
        run.queued_at = datetime.now(timezone.utc)
        run.started_at = None
        run.processed_at = None
        run.error_message = None
        db.commit()
        db.refresh(run)
        return run

    result = execute_run(run.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return result


@router.get("/{run_id}/trajectory.csv")
def download_trajectory(run_id: str, db: Session = Depends(get_db)) -> FileResponse:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if not run.result_csv_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trajectory is not generated yet",
        )
    if not Path(run.result_csv_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trajectory file is missing on disk",
        )
    return FileResponse(path=run.result_csv_path, filename=f"{run.id}_trajectory.csv")
