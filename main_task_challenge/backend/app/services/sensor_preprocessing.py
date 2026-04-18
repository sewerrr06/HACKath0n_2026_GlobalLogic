from __future__ import annotations

import bisect
import statistics
from dataclasses import dataclass

from app.services.fusion.math_utils import clamp01, vector_norm
from app.services.fusion.types import FusedImuFrame, ImuSample


@dataclass(slots=True)
class _PreparedStream:
    times: list[float]
    acc: list[tuple[float, float, float]]
    gyro: list[tuple[float, float, float]]
    base_weight: float


def _mad(values: list[float]) -> float:
    if not values:
        return 0.0
    median = statistics.median(values)
    absolute = [abs(value - median) for value in values]
    return statistics.median(absolute)


def remove_outliers(stream: list[ImuSample], z_threshold: float = 4.0) -> list[ImuSample]:
    if len(stream) < 8:
        return list(stream)

    acc_norms = [vector_norm(sample.acc) for sample in stream]
    gyro_norms = [vector_norm(sample.gyro) for sample in stream]

    acc_median = statistics.median(acc_norms)
    gyro_median = statistics.median(gyro_norms)
    acc_mad = _mad(acc_norms)
    gyro_mad = _mad(gyro_norms)
    if acc_mad <= 1e-9 or gyro_mad <= 1e-9:
        return list(stream)

    kept: list[ImuSample] = []
    for sample, acc_norm, gyro_norm in zip(stream, acc_norms, gyro_norms):
        acc_score = abs(acc_norm - acc_median) / (1.4826 * acc_mad)
        gyro_score = abs(gyro_norm - gyro_median) / (1.4826 * gyro_mad)
        if acc_score <= z_threshold and gyro_score <= z_threshold:
            kept.append(sample)

    return kept if kept else list(stream)


def _low_pass(values: list[tuple[float, float, float]], alpha: float) -> list[tuple[float, float, float]]:
    if not values:
        return []

    filtered: list[tuple[float, float, float]] = [values[0]]
    previous = values[0]
    for current in values[1:]:
        previous = tuple(
            alpha * current[index] + (1.0 - alpha) * previous[index] for index in range(3)
        )
        filtered.append(previous)
    return filtered


def _high_pass(values: list[tuple[float, float, float]], alpha: float) -> list[tuple[float, float, float]]:
    if not values:
        return []

    filtered: list[tuple[float, float, float]] = [values[0]]
    previous_input = values[0]
    previous_output = values[0]
    for current in values[1:]:
        output = tuple(
            alpha * (previous_output[index] + current[index] - previous_input[index])
            for index in range(3)
        )
        filtered.append(output)
        previous_input = current
        previous_output = output
    return filtered


def _estimate_noise(stream: list[ImuSample]) -> float:
    gyro_norms = [vector_norm(sample.gyro) for sample in stream]
    if len(gyro_norms) < 2:
        return 1e-3
    variance = statistics.pvariance(gyro_norms)
    return max(variance, 1e-6)


def _interp_scalar(times: list[float], values: list[float], t: float) -> float:
    idx = bisect.bisect_left(times, t)
    if idx <= 0:
        return values[0]
    if idx >= len(times):
        return values[-1]

    left_idx = idx - 1
    right_idx = idx
    left_time = times[left_idx]
    right_time = times[right_idx]
    if right_time - left_time <= 1e-9:
        return values[left_idx]
    fraction = (t - left_time) / (right_time - left_time)
    return values[left_idx] + fraction * (values[right_idx] - values[left_idx])


def _interp_vector(
    times: list[float],
    values: list[tuple[float, float, float]],
    t: float,
) -> tuple[float, float, float]:
    xs = [item[0] for item in values]
    ys = [item[1] for item in values]
    zs = [item[2] for item in values]
    return (
        _interp_scalar(times, xs, t),
        _interp_scalar(times, ys, t),
        _interp_scalar(times, zs, t),
    )


def _prepare_stream(stream: list[ImuSample]) -> _PreparedStream | None:
    if len(stream) < 5:
        return None

    cleaned = remove_outliers(stream)
    times = [sample.timestamp for sample in cleaned]
    acc_values = [sample.acc for sample in cleaned]
    gyro_values = [sample.gyro for sample in cleaned]

    filtered_acc = _low_pass(acc_values, alpha=0.22)
    filtered_gyro = _high_pass(gyro_values, alpha=0.85)

    return _PreparedStream(
        times=times,
        acc=filtered_acc,
        gyro=filtered_gyro,
        base_weight=1.0 / _estimate_noise(cleaned),
    )


def align_and_fuse_imus(imu_streams: dict[int, list[ImuSample]]) -> list[FusedImuFrame]:
    prepared_streams: list[_PreparedStream] = []
    for _, stream in sorted(imu_streams.items()):
        prepared = _prepare_stream(stream)
        if prepared is not None:
            prepared_streams.append(prepared)

    if not prepared_streams:
        return []

    reference = max(prepared_streams, key=lambda stream: len(stream.times))
    timeline = reference.times
    fused: list[FusedImuFrame] = []

    for t in timeline:
        candidates: list[tuple[tuple[float, float, float], tuple[float, float, float], float]] = []
        for stream in prepared_streams:
            if t < stream.times[0] or t > stream.times[-1]:
                continue
            acc = _interp_vector(stream.times, stream.acc, t)
            gyro = _interp_vector(stream.times, stream.gyro, t)
            candidates.append((acc, gyro, stream.base_weight))

        if not candidates:
            continue

        acc_norms = [vector_norm(candidate[0]) for candidate in candidates]
        median_acc_norm = statistics.median(acc_norms)

        dynamic_weights: list[float] = []
        for acc, _, base_weight in candidates:
            dynamic = 1.0 / (1.0 + abs(vector_norm(acc) - median_acc_norm))
            dynamic_weights.append(base_weight * dynamic)

        weight_sum = sum(dynamic_weights)
        if weight_sum <= 1e-9:
            continue

        acc_fused = [0.0, 0.0, 0.0]
        gyro_fused = [0.0, 0.0, 0.0]
        for (acc, gyro, _), weight in zip(candidates, dynamic_weights):
            normalized_weight = weight / weight_sum
            for axis in range(3):
                acc_fused[axis] += normalized_weight * acc[axis]
                gyro_fused[axis] += normalized_weight * gyro[axis]

        dispersion = statistics.pvariance(acc_norms) if len(acc_norms) > 1 else 0.0
        confidence = clamp01(1.0 / (1.0 + dispersion))

        fused.append(
            FusedImuFrame(
                timestamp=t,
                acc=(acc_fused[0], acc_fused[1], acc_fused[2]),
                gyro=(gyro_fused[0], gyro_fused[1], gyro_fused[2]),
                confidence=confidence,
            )
        )

    return fused
