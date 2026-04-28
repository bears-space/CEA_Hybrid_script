"""Simple thermal-resistance helpers for optional protection layers."""

from __future__ import annotations


def effective_gas_side_htc_with_protection(
    gas_side_htc_w_m2k: float,
    protection_thickness_m: float,
    protection_conductivity_w_mk: float,
) -> float:
    """Return the gas-to-base-wall effective HTC when a protection layer is present."""

    if protection_thickness_m <= 0.0:
        return float(gas_side_htc_w_m2k)
    if protection_conductivity_w_mk <= 0.0:
        raise ValueError("Protection conductivity must be positive.")
    resistance_gas = 1.0 / max(float(gas_side_htc_w_m2k), 1.0e-9)
    resistance_layer = float(protection_thickness_m) / float(protection_conductivity_w_mk)
    return 1.0 / max(resistance_gas + resistance_layer, 1.0e-9)
