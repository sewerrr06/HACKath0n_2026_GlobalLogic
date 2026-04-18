#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
from typing import Iterable

cache_dir = Path(".matplotlib-cache")
cache_dir.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir.resolve()))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir.resolve()))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
from pymavlink import mavutil

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build trajectory plots from ArduPilot BIN logs using GPS messages."
    )
    parser.add_argument(
        "logs",
        nargs="*",
        help="Paths to .BIN logs. If omitted, all .BIN files in the current directory are used.",
    )
    parser.add_argument(
        "--output-dir",
        default="plots",
        help="Directory where PNG plots will be written.",
    )
    parser.add_argument(
        "--gps-instance",
        type=int,
        default=0,
        help="GPS sensor instance to use from the GPS log message.",
    )
    parser.add_argument(
        "--min-status",
        type=int,
        default=1,
        help="Minimum GPS status required to keep a point.",
    )
    parser.add_argument(
        "--start-stage",
        "--stage-start",
        dest="start_stage",
        default="PAD_IDLE",
        help="Start flight stage for the plotted window. Use a name like PAD_IDLE or a numeric id.",
    )
    parser.add_argument(
        "--end-stage",
        "--stage-end",
        dest="end_stage",
        default="LANDED",
        help="End flight stage for the plotted window. Use a name like LANDED or a numeric id.",
    )
    parser.add_argument(
        "--fallback-end-stage",
        "--fallback-stage-end",
        dest="fallback_end_stage",
        default="DESCENT",
        help="Fallback end stage if --stage-end is missing. Use 'none' to disable fallback.",
    )
    parser.add_argument(
        "--full-log",
        action="store_true",
        help="Ignore FSTG stage limits and use the full log.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display figures interactively after saving them.",
    )
    return parser.parse_args()


def resolve_logs(log_args: list[str]) -> list[Path]:
    if log_args:
        logs = [Path(item) for item in log_args]
    else:
        logs = sorted(Path.cwd().glob("*.BIN"))

    return [path for path in logs if path.is_file()]


def parse_stage(value: str) -> int:
    normalized = value.strip().upper()
    if normalized.isdigit():
        return int(normalized)
    if normalized in STAGE_ALIASES:
        return STAGE_ALIASES[normalized]
    for stage_id, stage_name in STAGE_NAMES.items():
        if normalized == stage_name:
            return stage_id
    raise ValueError(f"Unknown flight stage: {value}")


def extract_stage_window(
    log_path: Path, start_stage: int, end_stage: int
) -> tuple[int | None, int | None]:
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
    log_path: Path, start_stage: int, end_stage: int, fallback_end_stage: int | None
) -> tuple[int | None, int | None, int | None]:
    start_time_us, end_time_us = extract_stage_window(log_path, start_stage, end_stage)
    if end_time_us is not None:
        return start_time_us, end_time_us, end_stage

    if fallback_end_stage is None:
        return start_time_us, None, None

    fallback_start_time_us, fallback_end_time_us = extract_stage_window(
        log_path, start_stage, fallback_end_stage
    )
    if start_time_us is None:
        start_time_us = fallback_start_time_us
    if fallback_end_time_us is not None:
        return start_time_us, fallback_end_time_us, fallback_end_stage

    return start_time_us, None, None


def extract_gps_points(
    log_path: Path,
    gps_instance: int,
    min_status: int,
    start_time_us: int | None,
    end_time_us: int | None,
) -> tuple[list[float], list[float]]:
    connection = mavutil.mavlink_connection(str(log_path))
    latitudes: list[float] = []
    longitudes: list[float] = []

    while True:
        message = connection.recv_match(type="GPS", blocking=False)
        if message is None:
            break

        data = message.to_dict()
        if data.get("I") != gps_instance:
            continue
        if data.get("Status", 0) < min_status:
            continue
        time_us = data.get("TimeUS")
        if start_time_us is not None and time_us is not None and time_us < start_time_us:
            continue
        if end_time_us is not None and time_us is not None and time_us > end_time_us:
            continue

        latitude = data.get("Lat")
        longitude = data.get("Lng")
        if latitude is None or longitude is None:
            continue

        latitudes.append(float(latitude))
        longitudes.append(float(longitude))

    return latitudes, longitudes


def to_local_coordinates(
    latitudes: list[float], longitudes: list[float]
) -> tuple[list[float], list[float]]:
    origin_lat_rad = math.radians(latitudes[0])
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = meters_per_degree_lat * math.cos(origin_lat_rad)

    east_m = [
        (longitude - longitudes[0]) * meters_per_degree_lon for longitude in longitudes
    ]
    north_m = [
        (latitude - latitudes[0]) * meters_per_degree_lat for latitude in latitudes
    ]
    min_east_m = min(east_m)
    min_north_m = min(north_m)
    east_m = [value - min_east_m for value in east_m]
    north_m = [value - min_north_m for value in north_m]
    return east_m, north_m


def build_plot(
    log_path: Path,
    latitudes: Iterable[float],
    longitudes: Iterable[float],
    stage_label: str,
) -> plt.Figure:
    latitudes = list(latitudes)
    longitudes = list(longitudes)
    east_m, north_m = to_local_coordinates(latitudes, longitudes)
    figure, axis = plt.subplots(figsize=(10, 8))
    axis.plot(east_m, north_m, linewidth=1.5, color="#1f77b4")
    axis.scatter(east_m[0], north_m[0], color="#2ca02c", s=50, label="start")
    axis.scatter(east_m[-1], north_m[-1], color="#d62728", s=50, label="finish")
    axis.set_title(f"Trajectory: {log_path.name}\n{stage_label}")
    axis.set_xlabel("Local east (m)")
    axis.set_ylabel("Local north (m)")
    axis.grid(True, linestyle="--", alpha=0.4)
    axis.set_aspect("equal", adjustable="box")
    axis.xaxis.set_major_formatter(ScalarFormatter(useOffset=False))
    axis.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
    axis.ticklabel_format(style="plain", axis="both")
    axis.legend()
    figure.tight_layout()
    return figure


def main() -> int:
    args = parse_args()
    logs = resolve_logs(args.logs)
    if not logs:
        print("No .BIN logs found.")
        return 1

    try:
        start_stage = parse_stage(args.start_stage)
        end_stage = parse_stage(args.end_stage)
        fallback_end_stage = (
            None
            if args.fallback_end_stage.strip().lower() == "none"
            else parse_stage(args.fallback_end_stage)
        )
    except ValueError as error:
        print(error)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    for log_path in logs:
        start_time_us: int | None = None
        end_time_us: int | None = None
        resolved_end_stage: int | None = end_stage
        stage_label = "FULL_LOG"
        if not args.full_log:
            start_time_us, end_time_us, resolved_end_stage = extract_stage_window_with_fallback(
                log_path,
                start_stage=start_stage,
                end_stage=end_stage,
                fallback_end_stage=fallback_end_stage,
            )
            if start_time_us is None:
                print(
                    f"Skipping {log_path.name}: stage {STAGE_NAMES.get(start_stage, start_stage)} not found."
                )
                continue
            if end_time_us is None:
                if fallback_end_stage is None:
                    print(
                        f"Skipping {log_path.name}: stage {STAGE_NAMES.get(end_stage, end_stage)} not found after "
                        f"{STAGE_NAMES.get(start_stage, start_stage)}."
                    )
                else:
                    print(
                        f"Skipping {log_path.name}: neither {STAGE_NAMES.get(end_stage, end_stage)} nor "
                        f"{STAGE_NAMES.get(fallback_end_stage, fallback_end_stage)} was found after "
                        f"{STAGE_NAMES.get(start_stage, start_stage)}."
                    )
                continue
            stage_label = (
                f"{STAGE_NAMES.get(start_stage, start_stage)} -> "
                f"{STAGE_NAMES.get(resolved_end_stage, resolved_end_stage)}"
            )

        latitudes, longitudes = extract_gps_points(
            log_path,
            gps_instance=args.gps_instance,
            min_status=args.min_status,
            start_time_us=start_time_us,
            end_time_us=end_time_us,
        )
        if len(latitudes) < 2:
            print(f"Skipping {log_path.name}: not enough valid GPS points.")
            continue

        figure = build_plot(log_path, latitudes, longitudes, stage_label=stage_label)
        output_path = output_dir / f"{log_path.stem}_trajectory.png"
        figure.savefig(output_path, dpi=200)
        print(f"Saved {output_path}")
        if not args.full_log:
            print(
                f"  Window: {STAGE_NAMES.get(start_stage, start_stage)} -> "
                f"{STAGE_NAMES.get(resolved_end_stage, resolved_end_stage)} "
                f"({start_time_us}us .. {end_time_us}us)"
            )
        processed += 1

        if args.show:
            plt.show()

        plt.close(figure)

    if processed == 0:
        print("No plots were created.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
