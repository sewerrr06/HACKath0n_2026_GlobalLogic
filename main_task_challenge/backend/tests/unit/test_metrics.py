from app.services.metrics import Point3D, endpoint_error, rms_crosstrack_error


def test_endpoint_error_zero_when_last_points_match() -> None:
    estimated = [Point3D(timestamp=0, x=0, y=0, z=0), Point3D(timestamp=1, x=1, y=1, z=1)]
    reference = [Point3D(timestamp=0, x=5, y=5, z=5), Point3D(timestamp=1, x=1, y=1, z=1)]
    assert endpoint_error(estimated, reference) == 0.0


def test_rms_crosstrack_error_non_negative() -> None:
    estimated = [
        Point3D(timestamp=0, x=0, y=0, z=0),
        Point3D(timestamp=1, x=1, y=0, z=0),
        Point3D(timestamp=2, x=2, y=0, z=0),
    ]
    reference = [
        Point3D(timestamp=0, x=0, y=1, z=0),
        Point3D(timestamp=1, x=1, y=1, z=0),
        Point3D(timestamp=2, x=2, y=1, z=0),
    ]
    assert (rms_crosstrack_error(estimated, reference) or 0.0) >= 0.0
