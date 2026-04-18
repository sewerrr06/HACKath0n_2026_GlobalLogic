from __future__ import annotations

from app.services.run_executor import execute_run
from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.process_run")
def process_run_task(run_id: str) -> dict[str, str]:
    run = execute_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id}")

    return {
        "run_id": run.id,
        "status": run.status.value,
    }
