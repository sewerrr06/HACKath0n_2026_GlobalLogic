from __future__ import annotations

import time
from datetime import datetime, timezone

from app.core.db import SessionLocal
from app.db.models import Run, RunStatus
from app.services.ins_pipeline import PipelineError, process_run


def execute_run(run_id: str) -> Run | None:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None:
            return None

        run.status = RunStatus.PROCESSING
        run.started_at = datetime.now(timezone.utc)
        run.error_message = None
        db.commit()

        wall_started = time.perf_counter()
        cpu_started = time.process_time()

        try:
            result = process_run(run)
        except PipelineError as error:
            run.status = RunStatus.FAILED
            run.error_message = str(error)
            run.processed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(run)
            return run
        except Exception as error:
            run.status = RunStatus.FAILED
            run.error_message = f"Unexpected error: {error}"
            run.processed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(run)
            return run

        wall_elapsed = time.perf_counter() - wall_started
        cpu_elapsed = time.process_time() - cpu_started

        run.status = RunStatus.COMPLETED
        run.result_csv_path = str(result.csv_path)
        run.point_count = result.point_count
        run.endpoint_error_m = result.endpoint_error_m
        run.rms_crosstrack_error_m = result.rms_crosstrack_error_m
        run.cpu_time_sec = cpu_elapsed
        run.wall_time_sec = wall_elapsed
        run.points_per_sec = (result.point_count / wall_elapsed) if wall_elapsed > 0 else None
        run.processed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run
    finally:
        db.close()
