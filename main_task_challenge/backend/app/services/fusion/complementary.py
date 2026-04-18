from __future__ import annotations

from app.services.fusion.base import FusionAlgorithm
from app.services.fusion.math_utils import clamp01, integrate_quaternion, rotate_vector, vector_norm
from app.services.fusion.types import FusedImuFrame, TrajectoryPoint

GRAVITY_MPS2 = 9.80665


class ComplementaryFusion(FusionAlgorithm):
    def __init__(
        self,
        zupt_acc_threshold: float = 0.25,
        zupt_gyro_threshold: float = 0.04,
        baro_blend: float = 0.08,
    ) -> None:
        self.zupt_acc_threshold = zupt_acc_threshold
        self.zupt_gyro_threshold = zupt_gyro_threshold
        self.baro_blend = baro_blend

    def run(
        self,
        frames: list[FusedImuFrame],
        baro_altitudes: list[float | None] | None = None,
    ) -> list[TrajectoryPoint]:
        if not frames:
            return []

        if baro_altitudes is None:
            baro_altitudes = [None] * len(frames)

        position = [0.0, 0.0, 0.0]
        velocity = [0.0, 0.0, 0.0]
        acc_bias = [0.0, 0.0, 0.0]
        quaternion = (1.0, 0.0, 0.0, 0.0)
        trajectory: list[TrajectoryPoint] = []

        previous_time = frames[0].timestamp
        for index, frame in enumerate(frames):
            dt = max(frame.timestamp - previous_time, 1e-3)
            previous_time = frame.timestamp

            quaternion = integrate_quaternion(quaternion, frame.gyro, dt)
            acceleration_world = rotate_vector(quaternion, frame.acc)
            linear_acceleration = (
                acceleration_world[0],
                acceleration_world[1],
                acceleration_world[2] - GRAVITY_MPS2,
            )

            static_state = (
                vector_norm(linear_acceleration) < self.zupt_acc_threshold
                and vector_norm(frame.gyro) < self.zupt_gyro_threshold
            )

            if static_state:
                for axis in range(3):
                    acc_bias[axis] = 0.98 * acc_bias[axis] + 0.02 * linear_acceleration[axis]

            corrected_acceleration = [
                linear_acceleration[axis] - acc_bias[axis] for axis in range(3)
            ]

            for axis in range(3):
                velocity[axis] += corrected_acceleration[axis] * dt

            if static_state:
                velocity = [0.0, 0.0, 0.0]

            for axis in range(3):
                position[axis] += velocity[axis] * dt

            baro_alt = baro_altitudes[index] if index < len(baro_altitudes) else None
            if baro_alt is not None:
                position[2] = (1.0 - self.baro_blend) * position[2] + self.baro_blend * baro_alt

            confidence = clamp01(frame.confidence - min(0.6, 0.015 * vector_norm(tuple(velocity))))

            trajectory.append(
                TrajectoryPoint(
                    timestamp=frame.timestamp,
                    x=position[0],
                    y=position[1],
                    z=position[2],
                    vx=velocity[0],
                    vy=velocity[1],
                    vz=velocity[2],
                    confidence=confidence,
                )
            )

        return trajectory
