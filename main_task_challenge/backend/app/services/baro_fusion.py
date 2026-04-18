from __future__ import annotations

import bisect
import math
import statistics

from app.services.fusion.types import BarometerSample


def pressure_to_altitude(pressure_pa: float, sea_level_pa: float = 101325.0) -> float:
    if pressure_pa <= 0:
        return 0.0
    return 44330.0 * (1.0 - (pressure_pa / sea_level_pa) ** (1.0 / 5.255))


def _to_altitude(sample: BarometerSample) -> float | None:
    if sample.altitude_m is not None:
        return sample.altitude_m
    if sample.pressure_pa is not None:
        return pressure_to_altitude(sample.pressure_pa)
    return None


def _estimate_noise(samples: list[BarometerSample]) -> float:
    values = [_to_altitude(sample) for sample in samples]
    valid = [value for value in values if value is not None]
    if len(valid) < 2:
        return 1.0
    return max(statistics.pvariance(valid), 1e-6)


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
    if abs(right_time - left_time) <= 1e-9:
        return values[left_idx]

    ratio = (t - left_time) / (right_time - left_time)
    return values[left_idx] + ratio * (values[right_idx] - values[left_idx])


def fuse_barometers(
    baro_streams: dict[int, list[BarometerSample]],
    timeline: list[float],
) -> list[float | None]:
    if not timeline:
        return []
    if not baro_streams:
        return [None] * len(timeline)

    prepared: list[tuple[list[float], list[float], float]] = []
    for _, samples in sorted(baro_streams.items()):
        samples = sorted(samples, key=lambda sample: sample.timestamp)
        times: list[float] = []
        values: list[float] = []
        for sample in samples:
            altitude = _to_altitude(sample)
            if altitude is None or math.isnan(altitude):
                continue
            times.append(sample.timestamp)
            values.append(altitude)
        if len(times) < 2:
            continue
        noise = _estimate_noise(samples)
        base_weight = 1.0 / noise
        prepared.append((times, values, base_weight))

    if not prepared:
        return [None] * len(timeline)

    fused: list[float | None] = []
    for t in timeline:
        weighted_sum = 0.0
        weight_sum = 0.0
        for times, values, base_weight in prepared:
            if t < times[0] or t > times[-1]:
                continue
            altitude = _interp_scalar(times, values, t)
            weighted_sum += base_weight * altitude
            weight_sum += base_weight

        if weight_sum <= 1e-9:
            fused.append(None)
            continue

        fused.append(weighted_sum / weight_sum)

    first_valid = next((value for value in fused if value is not None), None)
    if first_valid is None:
        return [None] * len(timeline)

    return [None if value is None else value - first_valid for value in fused]
