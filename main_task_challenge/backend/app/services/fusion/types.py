from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ImuSample:
    timestamp: float
    imu_id: int
    acc_x: float
    acc_y: float
    acc_z: float
    gyr_x: float
    gyr_y: float
    gyr_z: float

    @property
    def acc(self) -> tuple[float, float, float]:
        return (self.acc_x, self.acc_y, self.acc_z)

    @property
    def gyro(self) -> tuple[float, float, float]:
        return (self.gyr_x, self.gyr_y, self.gyr_z)


@dataclass(slots=True)
class BarometerSample:
    timestamp: float
    baro_id: int
    pressure_pa: float | None
    altitude_m: float | None
    temperature_c: float | None = None


@dataclass(slots=True)
class FusedImuFrame:
    timestamp: float
    acc: tuple[float, float, float]
    gyro: tuple[float, float, float]
    confidence: float


@dataclass(slots=True)
class TrajectoryPoint:
    timestamp: float
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    confidence: float
