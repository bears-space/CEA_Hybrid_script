"""Hydraulic and injector helper functions for the blowdown model."""

import math

from blowdown_hybrid.models import FeedConfig


def line_cross_section_area(line_id_m: float) -> float:
    return 0.25 * math.pi * line_id_m**2


def feed_pressure_drop_pa(mdot_kg_s: float, rho_kg_m3: float, feed: FeedConfig) -> float:
    """
    Lumped feed loss model:
        dp = (K_total + f * L / D) * (rho * v^2 / 2)
    """
    if mdot_kg_s <= 0.0:
        return 0.0
    area = line_cross_section_area(feed.line_id_m)
    velocity = mdot_kg_s / (rho_kg_m3 * area)
    loss_factor = feed.minor_loss_k_total + feed.friction_factor * (feed.line_length_m / feed.line_id_m)
    return 0.5 * rho_kg_m3 * velocity**2 * loss_factor


def injector_mdot_kg_s(cd: float, total_area_m2: float, rho_kg_m3: float, delta_p_pa: float) -> float:
    if delta_p_pa <= 0.0:
        return 0.0
    return cd * total_area_m2 * math.sqrt(2.0 * rho_kg_m3 * delta_p_pa)


def size_injector_total_area(
    target_mdot_ox_kg_s: float,
    tank_pressure_pa: float,
    chamber_pressure_pa: float,
    rho_liq_kg_m3: float,
    feed: FeedConfig,
    cd: float,
) -> float:
    """
    Size the total injector area from the design-point oxidizer flow.
    """
    dp_feed = feed_pressure_drop_pa(target_mdot_ox_kg_s, rho_liq_kg_m3, feed)
    dp_inj = tank_pressure_pa - dp_feed - chamber_pressure_pa
    if dp_inj <= 0.0:
        raise ValueError(
            "No positive injector delta-p at the design point. "
            "Increase tank pressure, reduce feed losses, or reduce chamber pressure."
        )
    return target_mdot_ox_kg_s / (cd * math.sqrt(2.0 * rho_liq_kg_m3 * dp_inj))


def equivalent_hole_diameter(total_area_m2: float, hole_count: int) -> float:
    if hole_count <= 0:
        raise ValueError("hole_count must be greater than zero.")
    area_per_hole = total_area_m2 / hole_count
    return math.sqrt(4.0 * area_per_hole / math.pi)
