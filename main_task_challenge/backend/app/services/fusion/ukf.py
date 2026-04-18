from __future__ import annotations

from collections import deque

from app.services.fusion.base import FusionAlgorithm
from app.services.fusion.ekf import EKFFusion
from app.services.fusion.math_utils import clamp01
from app.services.fusion.types import FusedImuFrame, TrajectoryPoint


class UKFFusion(FusionAlgorithm):
    """Starter UKF-like smoother using sigma-window averaging."""

    def __init__(self, sigma_window: int = 5) -> None:
        self.sigma_window = max(3, sigma_window)
        self.propagation = EKFFusion()

    def run(
        self,
        frames: list[FusedImuFrame],
        baro_altitudes: list[float | None] | None = None,
    ) -> list[TrajectoryPoint]:
        base = self.propagation.run(frames, baro_altitudes)
        if not base:
            return []

        xs: deque[float] = deque(maxlen=self.sigma_window)
        ys: deque[float] = deque(maxlen=self.sigma_window)
        zs: deque[float] = deque(maxlen=self.sigma_window)

        smoothed: list[TrajectoryPoint] = []
        for point in base:
            xs.append(point.x)
            ys.append(point.y)
            zs.append(point.z)

            x = sum(xs) / len(xs)
            y = sum(ys) / len(ys)
            z = sum(zs) / len(zs)

            smoothed.append(
                TrajectoryPoint(
                    timestamp=point.timestamp,
                    x=x,
                    y=y,
                    z=z,
                    vx=point.vx,
                    vy=point.vy,
                    vz=point.vz,
                    confidence=clamp01(point.confidence + 0.08),
                )
            )

        return smoothed
