from __future__ import annotations

from app.services.fusion.base import FusionAlgorithm
from app.services.fusion.complementary import ComplementaryFusion
from app.services.fusion.math_utils import clamp01
from app.services.fusion.types import FusedImuFrame, TrajectoryPoint


class EKFFusion(FusionAlgorithm):
    """Starter EKF-style smoothing over inertial propagation output."""

    def __init__(self) -> None:
        self.propagation = ComplementaryFusion(baro_blend=0.1)

    def run(
        self,
        frames: list[FusedImuFrame],
        baro_altitudes: list[float | None] | None = None,
    ) -> list[TrajectoryPoint]:
        base = self.propagation.run(frames, baro_altitudes)
        if not base:
            return []

        position = [base[0].x, base[0].y, base[0].z]
        variance = [1.0, 1.0, 1.0]
        smoothed: list[TrajectoryPoint] = []

        for point in base:
            process_noise = 0.03 + (1.0 - point.confidence) * 0.12
            measurement_noise = 0.1 + (1.0 - point.confidence) * 0.3

            output = [0.0, 0.0, 0.0]
            for axis, observed in enumerate((point.x, point.y, point.z)):
                variance[axis] += process_noise
                gain = variance[axis] / (variance[axis] + measurement_noise)
                position[axis] = position[axis] + gain * (observed - position[axis])
                variance[axis] = (1.0 - gain) * variance[axis]
                output[axis] = position[axis]

            smoothed.append(
                TrajectoryPoint(
                    timestamp=point.timestamp,
                    x=output[0],
                    y=output[1],
                    z=output[2],
                    vx=point.vx,
                    vy=point.vy,
                    vz=point.vz,
                    confidence=clamp01(point.confidence + 0.05),
                )
            )

        return smoothed
