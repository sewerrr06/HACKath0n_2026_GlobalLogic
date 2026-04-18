from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from pymavlink import mavutil

from app.core.config import Settings, get_settings
from app.db.models import Run
from app.services.baro_fusion import fuse_barometers
from app.services.fusion.factory import build_fusion_algorithm
from app.services.metrics import Point3D, endpoint_error, rms_crosstrack_error
from app.services.sensor_parsing import parse_sensor_log
from app.services.sensor_preprocessing import align_and_fuse_imus

STAGE_NAMES = {
    0: "INIT",
    1: "PAD_IDLE",
    2: "BOOST",
    3: "COAST",
    4: "APOGEE",
    5: "DESCENT",
    6: "LANDED",
}
STAGE_ALIASES = {
    "PADIDLE": 1,
    "PAD_IDLE": 1,
}


class PipelineError(RuntimeError):
    pass


@dataclass(slots=True)
class ProcessResult:
    csv_path: Path
    point_count: int
    endpoint_error_m: float | None
    rms_crosstrack_error_m: float | None


def parse_stage(value: str) -> int:
    normalized = value.strip().upper()
    if normalized.isdigit():
        return int(normalized)
    if normalized in STAGE_ALIASES:
        return STAGE_ALIASES[normalized]
    for stage_id, stage_name in STAGE_NAMES.items():
        if normalized == stage_name:
            return stage_id
    raise PipelineError(f"Unknown flight stage: {value}")


def resolve_path(raw_path: str, base_dir: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def extract_stage_window(log_path: Path, start_stage: int, end_stage: int) -> tuple[int | None, int | None]:
    connection = mavutil.mavlink_connection(str(log_path))
    start_time_us: int | None = None
    end_time_us: int | None = None

    while True:
        message = connection.recv_match(type="FSTG", blocking=False)
        if message is None:
            break

        data = message.to_dict()
        stage = data.get("Stg")
        time_us = data.get("TimeUS")
        if stage == start_stage and start_time_us is None:
            start_time_us = time_us
        if start_time_us is not None and stage == end_stage:
            end_time_us = time_us
            break

    return start_time_us, end_time_us


def extract_stage_window_with_fallback(
    log_path: Path,
    start_stage: int,
    end_stage: int,
    fallback_end_stage: int | None,
) -> tuple[int | None, int | None, int | None]:
    start_time_us, end_time_us = extract_stage_window(log_path, start_stage, end_stage)
    if end_time_us is not None:
        return start_time_us, end_time_us, end_stage

    if fallback_end_stage is None:
        return start_time_us, None, None

    fallback_start_time_us, fallback_end_time_us = extract_stage_window(
        log_path,
        start_stage,
        fallback_end_stage,
    )
    if start_time_us is None:
        start_time_us = fallback_start_time_us
    if fallback_end_time_us is not None:
        return start_time_us, fallback_end_time_us, fallback_end_stage

    return start_time_us, None, None


def read_ground_truth(path: Path) -> list[Point3D]:
    if not path.exists():
        raise PipelineError(f"Ground truth file does not exist: {path}")

    points: list[Point3D] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected_columns = {"timestamp", "x", "y", "z"}
        if not expected_columns.issubset(set(reader.fieldnames or [])):
            raise PipelineError(
                "Ground truth CSV must contain columns: timestamp, x, y, z"
            )
        for row in reader:
            points.append(
                Point3D(
                    timestamp=float(row["timestamp"]),
                    x=float(row["x"]),
                    y=float(row["y"]),
                    z=float(row["z"]),
                )
            )

    return points


def save_trajectory_csv(path: Path, points: list[Point3D]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "x", "y", "z"])
        for point in points:
            writer.writerow([point.timestamp, point.x, point.y, point.z])


def _resolve_stage_window(run: Run, log_path: Path) -> tuple[int | None, int | None]:
    start_stage = parse_stage(run.start_stage)
    end_stage = parse_stage(run.end_stage)
    fallback_end_stage = (
        None if run.fallback_end_stage is None else parse_stage(run.fallback_end_stage)
    )

    start_time_us, end_time_us, _ = extract_stage_window_with_fallback(
        log_path,
        start_stage=start_stage,
        end_stage=end_stage,
        fallback_end_stage=fallback_end_stage,
    )
    if start_time_us is None:
        raise PipelineError(
            f"Start stage {run.start_stage} was not found in {log_path.name}"
        )
    if end_time_us is None:
        raise PipelineError(
            f"End stage {run.end_stage} (or fallback) was not found in {log_path.name}"
        )

    return start_time_us, end_time_us


def _build_trajectory_points(run: Run, settings: Settings) -> list[Point3D]:
    log_path = resolve_path(run.log_path, settings.logs_dir)
    if not log_path.exists():
        raise PipelineError(f"Log file does not exist: {log_path}")

    start_time_us: int | None = None
    end_time_us: int | None = None
    if log_path.suffix.lower() == ".bin":
        start_time_us, end_time_us = _resolve_stage_window(run=run, log_path=log_path)

    parsed = parse_sensor_log(
        log_path=log_path,
        start_time_us=start_time_us,
        end_time_us=end_time_us,
    )
    if not parsed.imu_streams:
        raise PipelineError("No valid IMU samples found in input log")

    fused_frames = align_and_fuse_imus(parsed.imu_streams)
    if len(fused_frames) < 2:
        raise PipelineError("Not enough synchronized IMU frames after preprocessing")

    timeline = [frame.timestamp for frame in fused_frames]
    baro_altitudes = fuse_barometers(parsed.baro_streams, timeline)

    fusion = build_fusion_algorithm(settings.fusion_algorithm)
    trajectory = fusion.run(fused_frames, baro_altitudes)
    if len(trajectory) < 2:
        raise PipelineError("Fusion did not produce enough trajectory points")

    return [
        Point3D(timestamp=point.timestamp, x=point.x, y=point.y, z=point.z)
        for point in trajectory
    ]


def process_run(run: Run) -> ProcessResult:
    settings = get_settings()

    estimated_points = _build_trajectory_points(run=run, settings=settings)
    output_csv = settings.outputs_dir / run.id / "trajectory.csv"
    save_trajectory_csv(output_csv, estimated_points)

    endpoint: float | None = None
    rms: float | None = None
    if run.ground_truth_path:
        ground_truth = read_ground_truth(resolve_path(run.ground_truth_path, settings.logs_dir))
        endpoint = endpoint_error(estimated_points, ground_truth)
        rms = rms_crosstrack_error(estimated_points, ground_truth)

    return ProcessResult(
        csv_path=output_csv,
        point_count=len(estimated_points),
        endpoint_error_m=endpoint,
        rms_crosstrack_error_m=rms,
    )
