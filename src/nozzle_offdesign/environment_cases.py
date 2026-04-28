"""Ambient environment-case generation for nozzle off-design checks."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from src.nozzle_offdesign.ambient_profiles import (
    STANDARD_SEA_LEVEL_PRESSURE_PA,
    STANDARD_SEA_LEVEL_TEMPERATURE_K,
    pressure_from_altitude_m,
    temperature_from_altitude_m,
)
from src.nozzle_offdesign.nozzle_offdesign_types import AmbientEnvironmentCase


def _case_from_mapping(raw_case: Mapping[str, Any], index: int) -> AmbientEnvironmentCase:
    case = dict(raw_case)
    environment_type = str(case.get("environment_type", "user_override")).strip().lower()
    case_name = str(case.get("case_name", f"ambient_case_{index + 1}")).strip()
    altitude_m = float(case["altitude_m"]) if case.get("altitude_m") is not None else None
    ambient_pressure_pa = (
        float(case["ambient_pressure_pa"])
        if case.get("ambient_pressure_pa") is not None
        else (
            pressure_from_altitude_m(altitude_m)
            if altitude_m is not None
            else (0.0 if environment_type == "vacuum" else STANDARD_SEA_LEVEL_PRESSURE_PA)
        )
    )
    ambient_temperature_k = (
        float(case["ambient_temperature_k"])
        if case.get("ambient_temperature_k") is not None
        else (
            temperature_from_altitude_m(altitude_m)
            if altitude_m is not None
            else STANDARD_SEA_LEVEL_TEMPERATURE_K
        )
    )
    return AmbientEnvironmentCase(
        case_name=case_name,
        ambient_pressure_pa=ambient_pressure_pa,
        ambient_temperature_k=ambient_temperature_k,
        altitude_m=altitude_m,
        environment_type=environment_type,
        notes=[str(item) for item in case.get("notes", [])],
    )


def _sweep_cases(settings: Mapping[str, Any]) -> list[AmbientEnvironmentCase]:
    sweep = dict(settings.get("ambient_sweep", {}))
    if not bool(sweep.get("enabled", False)):
        return []
    minimum_altitude_m = float(sweep.get("minimum_altitude_m", 0.0))
    maximum_altitude_m = float(sweep.get("maximum_altitude_m", 30000.0))
    case_count = int(sweep.get("case_count", 6))
    altitudes = np.linspace(minimum_altitude_m, maximum_altitude_m, max(case_count, 2))
    cases = [
        AmbientEnvironmentCase(
            case_name=f"sweep_altitude_{int(round(altitude_m))}m",
            ambient_pressure_pa=pressure_from_altitude_m(float(altitude_m)),
            ambient_temperature_k=temperature_from_altitude_m(float(altitude_m)),
            altitude_m=float(altitude_m),
            environment_type="ascent_profile_point",
            notes=["Generated from the configured ambient sweep."],
        )
        for altitude_m in altitudes
    ]
    if bool(sweep.get("include_vacuum_case", True)):
        cases.append(
            AmbientEnvironmentCase(
                case_name="vacuum_sweep_endpoint",
                ambient_pressure_pa=0.0,
                ambient_temperature_k=None,
                altitude_m=None,
                environment_type="vacuum",
                notes=["Generated from the configured ambient sweep endpoint."],
            )
        )
    return cases


def _ascent_profile_cases(settings: Mapping[str, Any]) -> list[AmbientEnvironmentCase]:
    profile = dict(settings.get("ascent_profile", {}))
    if not bool(profile.get("enabled", False)):
        return []
    altitude_points = [float(value) for value in profile.get("altitude_points_m", [])]
    return [
        AmbientEnvironmentCase(
            case_name=f"profile_altitude_{int(round(altitude_m))}m",
            ambient_pressure_pa=pressure_from_altitude_m(altitude_m),
            ambient_temperature_k=temperature_from_altitude_m(altitude_m),
            altitude_m=altitude_m,
            environment_type="ascent_profile_point",
            notes=["Generated from the configured ascent-profile placeholder."],
        )
        for altitude_m in altitude_points
    ]


def build_environment_cases(nozzle_offdesign_config: Mapping[str, Any]) -> list[AmbientEnvironmentCase]:
    """Build the ambient environment cases requested by the nozzle off-design config."""

    settings = dict(nozzle_offdesign_config)
    explicit_cases = [
        _case_from_mapping(item, index)
        for index, item in enumerate(list(settings.get("ambient_cases", [])))
    ]
    cases = [*explicit_cases, *_sweep_cases(settings), *_ascent_profile_cases(settings)]
    deduped: list[AmbientEnvironmentCase] = []
    seen_names: set[str] = set()
    for case in cases:
        if case.case_name in seen_names:
            continue
        seen_names.add(case.case_name)
        deduped.append(case)
    return deduped
