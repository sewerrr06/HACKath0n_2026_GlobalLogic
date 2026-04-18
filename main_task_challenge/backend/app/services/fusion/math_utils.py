from __future__ import annotations

import math


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def vector_norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)


def quat_multiply(
    q1: tuple[float, float, float, float],
    q2: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def quat_normalize(quaternion: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    norm = math.sqrt(sum(component * component for component in quaternion))
    if norm <= 1e-9:
        return (1.0, 0.0, 0.0, 0.0)
    return tuple(component / norm for component in quaternion)


def quat_conjugate(quaternion: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    w, x, y, z = quaternion
    return (w, -x, -y, -z)


def integrate_quaternion(
    quaternion: tuple[float, float, float, float],
    gyro_rad_s: tuple[float, float, float],
    dt: float,
) -> tuple[float, float, float, float]:
    omega = (0.0, gyro_rad_s[0], gyro_rad_s[1], gyro_rad_s[2])
    derivative = quat_multiply(quaternion, omega)
    updated = (
        quaternion[0] + 0.5 * derivative[0] * dt,
        quaternion[1] + 0.5 * derivative[1] * dt,
        quaternion[2] + 0.5 * derivative[2] * dt,
        quaternion[3] + 0.5 * derivative[3] * dt,
    )
    return quat_normalize(updated)


def rotate_vector(
    quaternion: tuple[float, float, float, float],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    pure = (0.0, vector[0], vector[1], vector[2])
    rotated = quat_multiply(quat_multiply(quaternion, pure), quat_conjugate(quaternion))
    return (rotated[1], rotated[2], rotated[3])
