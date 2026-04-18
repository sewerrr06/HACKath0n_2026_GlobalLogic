from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class Point3D:
    timestamp: float
    x: float
    y: float
    z: float


def endpoint_error(estimated: list[Point3D], reference: list[Point3D]) -> float | None:
    if not estimated or not reference:
        return None
    p = estimated[-1]
    q = reference[-1]
    return math.sqrt((p.x - q.x) ** 2 + (p.y - q.y) ** 2 + (p.z - q.z) ** 2)


def rms_crosstrack_error(estimated: list[Point3D], reference: list[Point3D]) -> float | None:
    if not estimated or not reference:
        return None

    squared_errors: list[float] = []
    for point in estimated:
        nearest = min(reference, key=lambda r: (point.x - r.x) ** 2 + (point.y - r.y) ** 2)
        squared_errors.append((point.x - nearest.x) ** 2 + (point.y - nearest.y) ** 2)

    return math.sqrt(sum(squared_errors) / len(squared_errors))
