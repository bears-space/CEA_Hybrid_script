"""Minimal thrust-normalized nozzle sizing derived from CEA outputs."""

import math

from src.models.nozzle import (
    STANDARD_SEA_LEVEL_PRESSURE_PA,
    cf_vac_from_isp_and_cstar,
    evaluate_nozzle_performance,
)


G0_MPS2 = 9.80665
STANDARD_SEA_LEVEL_PRESSURE_BAR = 1.01325
DEFAULT_CF_SEARCH_UPPER_BOUND = 3.0
MIN_SUPERSONIC_AE_AT = 1.000001
CAP_MODE_EXIT_DIAMETER = "exit_diameter"
CAP_MODE_AREA_RATIO = "area_ratio"


def circle_area_from_diameter_m(diameter_m):
    return math.pi * diameter_m**2 / 4.0


def diameter_m_from_circle_area(area_m2):
    return math.sqrt(4.0 * area_m2 / math.pi)


def estimate_ae_at_search_stop(target_thrust_n, pc_bar, max_exit_diameter_cm, cf_upper_bound):
    """Return a conservative Ae/At search ceiling.

    The true exit-diameter cap depends on CEA's thrust coefficient, which depends
    on the requested area ratio. This upper bound only sizes a candidate grid; a
    separate per-case diameter check rejects candidates that exceed the physical
    exit-diameter limit.
    """
    pc_pa = pc_bar * 1e5
    max_exit_area_m2 = circle_area_from_diameter_m(max_exit_diameter_cm / 100.0)
    return max(MIN_SUPERSONIC_AE_AT, max_exit_area_m2 * pc_pa * cf_upper_bound / target_thrust_n)


def _normalize_ae_at_start(value):
    return max(MIN_SUPERSONIC_AE_AT, float(value))


def _build_ae_at_values(start, stop, step):
    start = _normalize_ae_at_start(start)
    stop = float(stop)
    step = float(step)
    if step <= 0.0:
        raise ValueError("sweeps.ae_at.step must be positive.")
    if stop < start:
        raise ValueError("sweeps.ae_at.stop must be greater than or equal to the start value.")

    values = []
    current = start
    tolerance = step * 1e-9
    while current <= stop + tolerance:
        values.append(current)
        current += step
    if values[-1] < stop:
        values.append(stop)
    return values


def build_ae_at_values(
    raw_ae_at,
    target_thrust_n,
    pc_bar,
    cap_mode,
    max_exit_diameter_cm=None,
    max_area_ratio=None,
):
    cf_upper_bound = float(raw_ae_at.get("cf_search_upper_bound", DEFAULT_CF_SEARCH_UPPER_BOUND))
    if cf_upper_bound <= 0.0:
        raise ValueError("sweeps.ae_at.cf_search_upper_bound must be positive.")

    if cap_mode == CAP_MODE_AREA_RATIO:
        if max_area_ratio is None:
            raise ValueError("max_area_ratio is required when ae_at_cap_mode is 'area_ratio'.")
        default_stop = float(max_area_ratio)
    elif cap_mode == CAP_MODE_EXIT_DIAMETER:
        if max_exit_diameter_cm is None:
            raise ValueError("max_exit_diameter_cm is required when ae_at_cap_mode is 'exit_diameter'.")
        default_stop = estimate_ae_at_search_stop(
            target_thrust_n,
            pc_bar,
            float(max_exit_diameter_cm),
            cf_upper_bound,
        )
    else:
        raise ValueError("ae_at_cap_mode must be 'exit_diameter' or 'area_ratio'.")

    if bool(raw_ae_at.get("custom_enabled", False)):
        start = raw_ae_at.get("start", 1.0)
        stop = raw_ae_at.get("stop", default_stop)
        step = raw_ae_at.get("step", 1.0)
        if cap_mode == CAP_MODE_AREA_RATIO:
            stop = min(float(stop), float(max_area_ratio))
        return _build_ae_at_values(start, stop, step)

    return _build_ae_at_values(1.0, default_stop, raw_ae_at.get("step", 1.0))


def add_nozzle_sizing(case, config):
    target_thrust_n = config["target_thrust_n"]
    pc_pa = case["pc_bar"] * 1e5
    mdot_total = target_thrust_n / case["isp_mps"]
    at_m2 = mdot_total * case["cstar_mps"] / pc_pa
    ae_m2 = case["ae_at"] * at_m2
    cf_sl = case["isp_mps"] / case["cstar_mps"]
    cf_vac = cf_vac_from_isp_and_cstar(case["isp_vac_mps"] / G0_MPS2, case["cstar_mps"])
    nozzle = evaluate_nozzle_performance(
        cstar_mps=case["cstar_mps"],
        cf_vac=cf_vac,
        chamber_pressure_pa=pc_pa,
        throat_area_m2=at_m2,
        mdot_total_kg_s=mdot_total,
        ambient_pressure_pa=STANDARD_SEA_LEVEL_PRESSURE_PA,
        exit_area_m2=ae_m2,
        exit_pressure_ratio=case["pe_bar"] / case["pc_bar"],
        gamma_e=case["gamma_e"],
        molecular_weight_exit=case["mw_e"],
    )
    dt_m = diameter_m_from_circle_area(at_m2)
    de_m = diameter_m_from_circle_area(ae_m2)
    max_exit_diameter_cm = config.get("max_exit_diameter_cm")
    cap_mode = config.get("ae_at_cap_mode", CAP_MODE_EXIT_DIAMETER)
    de_cm = de_m * 100.0

    sized = {
        **case,
        "target_thrust_n": target_thrust_n,
        "max_exit_diameter_cm": max_exit_diameter_cm,
        "max_area_ratio": config.get("max_area_ratio"),
        "ae_at_cap_mode": cap_mode,
        "mdot_total_kg_s": mdot_total,
        "at_m2": at_m2,
        "ae_m2": ae_m2,
        "thrust_ideal_vac_n": nozzle.thrust_vac_n,
        "thrust_vac_n": nozzle.thrust_vac_n,
        "thrust_sea_level_n": nozzle.thrust_actual_n,
        "thrust_sl_n": nozzle.thrust_actual_n,
        "dt_mm": dt_m * 1e3,
        "de_mm": de_m * 1e3,
        "de_cm": de_cm,
        "cf_ideal": cf_vac,
        "cf_actual": cf_sl,
        "cf_sea_level": cf_sl,
        "cf_vac": cf_vac,
        "isp_s": nozzle.isp_actual_s,
        "isp_sl_s": nozzle.isp_actual_s,
        "isp_vac_s": nozzle.isp_vac_s,
        "exit_diameter_margin_cm": None,
        "exit_diameter_within_limit": True,
    }

    if cap_mode == CAP_MODE_EXIT_DIAMETER and max_exit_diameter_cm is not None:
        margin_cm = max_exit_diameter_cm - de_cm
        sized.update(
            {
                "exit_diameter_margin_cm": margin_cm,
                "exit_diameter_within_limit": margin_cm >= -1e-9,
            }
        )
    return sized
