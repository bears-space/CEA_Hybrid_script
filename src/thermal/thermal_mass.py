"""Mass-estimation helpers for first-pass thermal protection."""

from __future__ import annotations

from src.thermal.thermal_types import ThermalProtectionSizingResult


def estimate_thermal_protection_mass_kg(
    liner_result: ThermalProtectionSizingResult | None,
    throat_insert_result: ThermalProtectionSizingResult | None,
) -> float:
    """Return the combined thermal-protection placeholder mass."""

    total = 0.0
    if liner_result is not None:
        total += float(liner_result.mass_estimate_kg)
    if throat_insert_result is not None:
        total += float(throat_insert_result.mass_estimate_kg)
    return total
