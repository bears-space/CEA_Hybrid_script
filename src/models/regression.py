"""Reusable local regression-law helpers for the 1D internal ballistics model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PowerLawRegressionModel:
    """Baseline hybrid regression law with optional multiplicative correction."""

    a_reg_si: float
    n_reg: float

    def rate_m_s(self, oxidizer_flux_kg_m2_s: float, correction_factor: float = 1.0) -> float:
        flux = max(float(oxidizer_flux_kg_m2_s), 0.0) * max(float(correction_factor), 0.0)
        return self.a_reg_si * flux**self.n_reg


def fuel_addition_rate_kg_s(
    *,
    fuel_density_kg_m3: float,
    port_radius_m: float,
    cell_length_m: float,
    port_count: int,
    regression_rate_m_s: float,
) -> float:
    wetted_perimeter_m = int(port_count) * 2.0 * 3.141592653589793 * float(port_radius_m)
    return float(fuel_density_kg_m3) * wetted_perimeter_m * float(cell_length_m) * float(regression_rate_m_s)
