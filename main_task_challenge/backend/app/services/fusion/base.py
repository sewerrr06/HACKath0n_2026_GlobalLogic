from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.fusion.types import FusedImuFrame, TrajectoryPoint


class FusionAlgorithm(ABC):
    @abstractmethod
    def run(
        self,
        frames: list[FusedImuFrame],
        baro_altitudes: list[float | None] | None = None,
    ) -> list[TrajectoryPoint]:
        raise NotImplementedError
