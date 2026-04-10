"""Adapters that convert legacy CEA dictionaries into typed result objects."""

from __future__ import annotations

from typing import Any

from src.cea.cea_types import CEACaseInput, CEAPerformancePoint, CEASweepResult


def dict_to_performance_point(row: dict[str, Any]) -> CEAPerformancePoint:
    case_input = CEACaseInput(
        abs_volume_fraction=float(row["abs_vol_frac"]),
        fuel_temperature_k=float(row["fuel_temp_k"]),
        oxidizer_temperature_k=float(row["oxidizer_temp_k"]),
        of_ratio=float(row["of"]),
        pc_bar=float(row["pc_bar"]),
        ae_at=float(row["ae_at"]),
    )
    return CEAPerformancePoint(
        case_input=case_input,
        target_thrust_n=float(row["target_thrust_n"]),
        cstar_mps=float(row["cstar_mps"]),
        isp_s=float(row["isp_s"]),
        isp_sl_s=float(row.get("isp_sl_s", row["isp_s"])),
        isp_vac_s=float(row["isp_vac_s"]),
        cf=float(row["cf"]),
        cf_sea_level=float(row.get("cf_sea_level", row.get("cf_actual", row["cf"]))),
        cf_vac=float(row.get("cf_vac", row["cf"])),
        gamma_e=float(row["gamma_e"]),
        molecular_weight_exit=float(row["mw_e"]),
        chamber_temperature_k=float(row["tc_k"]),
        exit_pressure_bar=float(row["pe_bar"]),
        exit_temperature_k=float(row["te_k"]),
        throat_area_m2=float(row["at_m2"]),
        exit_area_m2=float(row["ae_m2"]),
        thrust_sea_level_n=float(row.get("thrust_sea_level_n", row.get("thrust_sl_n", row["target_thrust_n"]))),
        thrust_vac_n=float(row.get("thrust_vac_n", row.get("target_thrust_n", row["thrust_sl_n"]))),
        raw=dict(row),
    )


def dict_to_sweep_result(config: dict[str, Any], payload: dict[str, Any]) -> CEASweepResult:
    return CEASweepResult(
        config=config,
        cases=[dict_to_performance_point(case) for case in payload["cases"]],
        failures=[dict(item) for item in payload["failures"]],
        total_combinations=int(payload["total_combinations"]),
        cpu_workers=int(payload["cpu_workers"]),
        backend=str(payload["backend"]),
        gpu_enabled=bool(payload["gpu_enabled"]),
    )


def load_or_parse_cea_result(result: Any) -> CEAPerformancePoint | CEASweepResult:
    if isinstance(result, (CEAPerformancePoint, CEASweepResult)):
        return result
    if isinstance(result, dict) and "cases" in result and "failures" in result:
        config = dict(result.get("config", {}))
        return dict_to_sweep_result(config, result)
    if isinstance(result, dict):
        return dict_to_performance_point(result)
    raise TypeError(f"Unsupported CEA result payload: {type(result)!r}")
