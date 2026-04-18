from __future__ import annotations

from app.services.fusion.base import FusionAlgorithm
from app.services.fusion.complementary import ComplementaryFusion
from app.services.fusion.ekf import EKFFusion
from app.services.fusion.ukf import UKFFusion


def build_fusion_algorithm(name: str) -> FusionAlgorithm:
    key = name.strip().lower()
    if key in {"complementary", "comp"}:
        return ComplementaryFusion()
    if key == "ukf":
        return UKFFusion()
    return EKFFusion()
