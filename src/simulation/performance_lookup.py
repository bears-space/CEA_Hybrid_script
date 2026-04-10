"""Lightweight cached CEA lookup support for transient c* and nozzle performance."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from typing import Any, Mapping

import numpy as np

from blowdown_hybrid.constants import G0_MPS2
from cea_hybrid.defaults import get_default_raw_config

from src.cea.cea_runner import run_cea_case
from src.io_utils import deep_merge
from src.models.nozzle import STANDARD_SEA_LEVEL_PRESSURE_PA, evaluate_nozzle_performance


@dataclass(frozen=True)
class PerformanceLookupTable:
    of_values: tuple[float, ...]
    cstar_mps_values: tuple[float, ...]
    cf_vac_values: tuple[float, ...]
    cf_sea_level_values: tuple[float, ...]
    gamma_e_values: tuple[float, ...]
    molecular_weight_exit_values: tuple[float, ...]
    exit_pressure_ratio_values: tuple[float, ...]
    pc_reference_pa: float
    ambient_reference_pa: float
    ae_at: float

    def _interp(self, values: tuple[float, ...], of_ratio: float) -> float:
        return float(np.interp(float(of_ratio), self.of_values, values))

    def evaluate(
        self,
        of_ratio: float,
        chamber_pressure_pa: float,
        ambient_pressure_pa: float,
        throat_area_m2: float,
        exit_area_m2: float,
        mdot_total_kg_s: float,
    ) -> dict[str, float]:
        cstar_mps = self._interp(self.cstar_mps_values, of_ratio)
        cf_vac = self._interp(self.cf_vac_values, of_ratio)
        gamma_e = self._interp(self.gamma_e_values, of_ratio)
        molecular_weight_exit = self._interp(self.molecular_weight_exit_values, of_ratio)
        exit_pressure_ratio = self._interp(self.exit_pressure_ratio_values, of_ratio)
        nozzle = evaluate_nozzle_performance(
            cstar_mps=cstar_mps,
            cf_vac=cf_vac,
            chamber_pressure_pa=chamber_pressure_pa,
            throat_area_m2=throat_area_m2,
            mdot_total_kg_s=mdot_total_kg_s,
            ambient_pressure_pa=ambient_pressure_pa,
            exit_area_m2=exit_area_m2,
            exit_pressure_ratio=exit_pressure_ratio,
            gamma_e=gamma_e,
            molecular_weight_exit=molecular_weight_exit,
        )
        return {
            "cstar_mps": nozzle.cstar_mps,
            "cf_vac": nozzle.cf_vac,
            "cf_actual": nozzle.cf_actual,
            "isp_vac_s": nozzle.isp_vac_s,
            "isp_actual_s": nozzle.isp_actual_s,
            "thrust_vac_n": nozzle.thrust_vac_n,
            "thrust_actual_n": nozzle.thrust_actual_n,
            "exit_pressure_pa": 0.0 if nozzle.exit_pressure_pa is None else nozzle.exit_pressure_pa,
            "gamma_e": 0.0 if nozzle.gamma_e is None else nozzle.gamma_e,
            "molecular_weight_exit": 0.0 if nozzle.molecular_weight_exit is None else nozzle.molecular_weight_exit,
        }


def _sample_of_values(center_of_ratio: float, padding: float, sample_count: int) -> tuple[float, ...]:
    low = max(0.2, float(center_of_ratio) - float(padding))
    high = max(low + 1e-6, float(center_of_ratio) + float(padding))
    return tuple(float(value) for value in np.linspace(low, high, int(sample_count)))


def _lookup_cache_key(seed_case: Mapping[str, Any], lookup_config: Mapping[str, Any], raw_cea_config: Mapping[str, Any]) -> str:
    payload = {
        "seed_case": {
            "target_thrust_n": float(seed_case["target_thrust_n"]),
            "of": float(seed_case["of"]),
            "pc_bar": float(seed_case["pc_bar"]),
            "fuel_temp_k": float(seed_case["fuel_temp_k"]),
            "oxidizer_temp_k": float(seed_case["oxidizer_temp_k"]),
            "abs_vol_frac": float(seed_case["abs_vol_frac"]),
            "ae_at": float(seed_case["ae_m2"]) / float(seed_case["at_m2"]),
        },
        "lookup_config": {
            "of_padding": float(lookup_config["of_padding"]),
            "sample_count": int(lookup_config["sample_count"]),
        },
        "cea_base": {
            "iac": bool(raw_cea_config.get("iac", True)),
            "max_exit_diameter_cm": float(raw_cea_config.get("max_exit_diameter_cm", 12.0)),
            "max_area_ratio": float(raw_cea_config.get("max_area_ratio", 24.0)),
            "ae_at_cap_mode": raw_cea_config.get("ae_at_cap_mode", "exit_diameter"),
        },
    }
    return json.dumps(payload, sort_keys=True)


@lru_cache(maxsize=64)
def _build_lookup_cached(serialized_key: str) -> PerformanceLookupTable:
    payload = json.loads(serialized_key)
    seed_case = payload["seed_case"]
    lookup_config = payload["lookup_config"]
    cea_base = payload["cea_base"]

    raw_cea_config = deep_merge(get_default_raw_config(), cea_base)
    of_values = _sample_of_values(seed_case["of"], lookup_config["of_padding"], lookup_config["sample_count"])

    cstar_values: list[float] = []
    cf_vac_values: list[float] = []
    cf_sl_values: list[float] = []
    gamma_values: list[float] = []
    molecular_weight_values: list[float] = []
    exit_pressure_ratio_values: list[float] = []

    for of_ratio in of_values:
        case = run_cea_case(
            {
                "base_config": raw_cea_config,
                "case_input": {
                    "target_thrust_n": seed_case["target_thrust_n"],
                    "pc_bar": seed_case["pc_bar"],
                    "abs_vol_frac": seed_case["abs_vol_frac"],
                    "fuel_temp_k": seed_case["fuel_temp_k"],
                    "oxidizer_temp_k": seed_case["oxidizer_temp_k"],
                    "of": of_ratio,
                    "ae_at": seed_case["ae_at"],
                    "max_exit_diameter_cm": raw_cea_config["max_exit_diameter_cm"],
                    "max_area_ratio": raw_cea_config.get("max_area_ratio", 24.0),
                    "ae_at_cap_mode": raw_cea_config.get("ae_at_cap_mode", "exit_diameter"),
                },
            }
        )
        cstar_values.append(case.cstar_mps)
        cf_vac_values.append(case.isp_vac_s * G0_MPS2 / case.cstar_mps)
        cf_sl_values.append(case.isp_sl_s * G0_MPS2 / case.cstar_mps)
        gamma_values.append(case.gamma_e)
        molecular_weight_values.append(case.molecular_weight_exit)
        exit_pressure_ratio_values.append(case.exit_pressure_bar / case.case_input.pc_bar)

    return PerformanceLookupTable(
        of_values=of_values,
        cstar_mps_values=tuple(cstar_values),
        cf_vac_values=tuple(cf_vac_values),
        cf_sea_level_values=tuple(cf_sl_values),
        gamma_e_values=tuple(gamma_values),
        molecular_weight_exit_values=tuple(molecular_weight_values),
        exit_pressure_ratio_values=tuple(exit_pressure_ratio_values),
        pc_reference_pa=float(seed_case["pc_bar"]) * 1.0e5,
        ambient_reference_pa=STANDARD_SEA_LEVEL_PRESSURE_PA,
        ae_at=float(seed_case["ae_at"]),
    )


def build_performance_lookup(
    seed_case: Mapping[str, Any],
    lookup_config: Mapping[str, Any] | None,
    raw_cea_config: Mapping[str, Any] | None = None,
) -> PerformanceLookupTable:
    config = {
        "enabled": True,
        "of_padding": 2.0,
        "sample_count": 9,
        **dict(lookup_config or {}),
    }
    if not bool(config.get("enabled", True)):
        raise ValueError("Performance lookup is disabled.")
    sample_count = int(config["sample_count"])
    if sample_count < 2:
        raise ValueError("performance_lookup.sample_count must be at least 2.")
    raw = deep_merge(get_default_raw_config(), raw_cea_config or {})
    key = _lookup_cache_key(seed_case, {"of_padding": config["of_padding"], "sample_count": sample_count}, raw)
    return _build_lookup_cached(key)
