from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pymavlink import mavutil

from app.services.fusion.types import BarometerSample, ImuSample


@dataclass(slots=True)
class ParsedSensorLog:
    imu_streams: dict[int, list[ImuSample]]
    baro_streams: dict[int, list[BarometerSample]]


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int_or_default(value: object, default: int = 0) -> int:
    maybe = _float_or_none(value)
    if maybe is None:
        return default
    return int(maybe)


def _first_not_none(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _merge_imu_stream(
    imu_id: int,
    acc_rows: list[tuple[float, tuple[float, float, float]]],
    gyr_rows: list[tuple[float, tuple[float, float, float]]],
    max_delta_s: float = 0.02,
) -> list[ImuSample]:
    merged: list[ImuSample] = []
    acc_rows.sort(key=lambda row: row[0])
    gyr_rows.sort(key=lambda row: row[0])

    i = 0
    j = 0
    while i < len(acc_rows) and j < len(gyr_rows):
        acc_time, acc = acc_rows[i]
        gyr_time, gyro = gyr_rows[j]
        delta = acc_time - gyr_time
        if abs(delta) <= max_delta_s:
            timestamp = 0.5 * (acc_time + gyr_time)
            merged.append(
                ImuSample(
                    timestamp=timestamp,
                    imu_id=imu_id,
                    acc_x=acc[0],
                    acc_y=acc[1],
                    acc_z=acc[2],
                    gyr_x=gyro[0],
                    gyr_y=gyro[1],
                    gyr_z=gyro[2],
                )
            )
            i += 1
            j += 1
            continue

        if delta < 0:
            i += 1
        else:
            j += 1

    return merged


def _within_stage_window(
    time_us: float,
    start_time_us: int | None,
    end_time_us: int | None,
) -> bool:
    if start_time_us is not None and time_us < start_time_us:
        return False
    if end_time_us is not None and time_us > end_time_us:
        return False
    return True


def parse_bin_sensor_log(
    log_path: Path,
    start_time_us: int | None,
    end_time_us: int | None,
) -> ParsedSensorLog:
    imu_acc: dict[int, list[tuple[float, tuple[float, float, float]]]] = defaultdict(list)
    imu_gyr: dict[int, list[tuple[float, tuple[float, float, float]]]] = defaultdict(list)
    baro_streams: dict[int, list[BarometerSample]] = defaultdict(list)

    connection = mavutil.mavlink_connection(str(log_path))
    message_types = ["ACC", "GYR", "BARO", "BAR2", "BAR3", "BAR4"]

    while True:
        message = connection.recv_match(type=message_types, blocking=False)
        if message is None:
            break

        data = message.to_dict()
        msg_type = message.get_type()
        time_us = _first_not_none(
            _float_or_none(data.get("TimeUS")),
            _float_or_none(data.get("SampleUS")),
        )
        if time_us is None:
            continue
        if not _within_stage_window(time_us, start_time_us, end_time_us):
            continue

        timestamp = time_us / 1_000_000.0

        if msg_type == "ACC":
            imu_id = _int_or_default(data.get("I"), default=0)
            acc_x = _float_or_none(data.get("AccX"))
            acc_y = _float_or_none(data.get("AccY"))
            acc_z = _float_or_none(data.get("AccZ"))
            if acc_x is None or acc_y is None or acc_z is None:
                continue
            imu_acc[imu_id].append((timestamp, (acc_x, acc_y, acc_z)))
            continue

        if msg_type == "GYR":
            imu_id = _int_or_default(data.get("I"), default=0)
            gyr_x = _float_or_none(data.get("GyrX"))
            gyr_y = _float_or_none(data.get("GyrY"))
            gyr_z = _float_or_none(data.get("GyrZ"))
            if gyr_x is None or gyr_y is None or gyr_z is None:
                continue
            imu_gyr[imu_id].append((timestamp, (gyr_x, gyr_y, gyr_z)))
            continue

        baro_id = _int_or_default(data.get("I"), default=0)
        pressure = _first_not_none(
            _float_or_none(data.get("Press")),
            _float_or_none(data.get("PressAbs")),
            _float_or_none(data.get("PressPa")),
            _float_or_none(data.get("Pressure")),
        )
        altitude = _first_not_none(_float_or_none(data.get("Alt")), _float_or_none(data.get("AltM")))
        temperature = _first_not_none(_float_or_none(data.get("Temp")), _float_or_none(data.get("TempC")))
        if pressure is None and altitude is None:
            continue
        baro_streams[baro_id].append(
            BarometerSample(
                timestamp=timestamp,
                baro_id=baro_id,
                pressure_pa=pressure,
                altitude_m=altitude,
                temperature_c=temperature,
            )
        )

    imu_streams: dict[int, list[ImuSample]] = {}
    for imu_id in sorted(set(imu_acc) | set(imu_gyr)):
        merged = _merge_imu_stream(
            imu_id=imu_id,
            acc_rows=imu_acc.get(imu_id, []),
            gyr_rows=imu_gyr.get(imu_id, []),
        )
        if merged:
            imu_streams[imu_id] = merged

    for baro_id, samples in baro_streams.items():
        samples.sort(key=lambda item: item.timestamp)

    return ParsedSensorLog(imu_streams=imu_streams, baro_streams=dict(baro_streams))


def parse_csv_sensor_log(log_path: Path) -> ParsedSensorLog:
    imu_streams: dict[int, list[ImuSample]] = defaultdict(list)
    baro_streams: dict[int, list[BarometerSample]] = defaultdict(list)

    with log_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            timestamp = _first_not_none(
                _float_or_none(row.get("timestamp")),
                _float_or_none(row.get("time")),
                _float_or_none(row.get("time_s")),
            )
            if timestamp is None:
                continue

            imu_id = _int_or_default(row.get("imu_id"), default=0)
            acc_x = _float_or_none(row.get("acc_x"))
            acc_y = _float_or_none(row.get("acc_y"))
            acc_z = _float_or_none(row.get("acc_z"))
            gyr_x = _float_or_none(row.get("gyr_x"))
            gyr_y = _float_or_none(row.get("gyr_y"))
            gyr_z = _float_or_none(row.get("gyr_z"))

            if None not in {acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z}:
                imu_streams[imu_id].append(
                    ImuSample(
                        timestamp=float(timestamp),
                        imu_id=imu_id,
                        acc_x=float(acc_x),
                        acc_y=float(acc_y),
                        acc_z=float(acc_z),
                        gyr_x=float(gyr_x),
                        gyr_y=float(gyr_y),
                        gyr_z=float(gyr_z),
                    )
                )

            baro_id = _int_or_default(row.get("baro_id"), default=0)
            pressure = _float_or_none(row.get("pressure_pa"))
            altitude = _float_or_none(row.get("baro_alt_m"))
            temperature = _float_or_none(row.get("temperature_c"))
            if pressure is not None or altitude is not None:
                baro_streams[baro_id].append(
                    BarometerSample(
                        timestamp=float(timestamp),
                        baro_id=baro_id,
                        pressure_pa=pressure,
                        altitude_m=altitude,
                        temperature_c=temperature,
                    )
                )

    for streams in (imu_streams, baro_streams):
        for _, values in streams.items():
            values.sort(key=lambda item: item.timestamp)

    return ParsedSensorLog(imu_streams=dict(imu_streams), baro_streams=dict(baro_streams))


def parse_sensor_log(
    log_path: Path,
    start_time_us: int | None = None,
    end_time_us: int | None = None,
) -> ParsedSensorLog:
    suffix = log_path.suffix.lower()
    if suffix == ".bin":
        return parse_bin_sensor_log(log_path, start_time_us=start_time_us, end_time_us=end_time_us)
    if suffix == ".csv":
        return parse_csv_sensor_log(log_path)
    raise ValueError(f"Unsupported sensor log format: {log_path.suffix}")
