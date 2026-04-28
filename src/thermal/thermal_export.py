"""Thermal output export, reports, and lightweight plots."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src.io_utils import write_json
from src.post.csv_export import write_rows_csv
from src.post.plotting import write_grouped_horizontal_bar_chart, write_horizontal_bar_chart, write_line_plot
from src.thermal.thermal_types import ThermalLoadCase, ThermalSizingResult


def _region_rows(result: ThermalSizingResult) -> list[dict[str, float | str | bool | None]]:
    base_rows = [
        {
            "region": "chamber",
            "peak_heat_flux_w_m2": result.chamber_region_result.region.peak_heat_flux_w_m2,
            "peak_inner_wall_temp_k": result.chamber_region_result.region.peak_inner_wall_temp_k,
            "allowable_temp_k": result.chamber_region_result.region.max_allowable_temp_k,
            "thermal_margin_k": result.chamber_region_result.region.thermal_margin_k,
            "valid": result.chamber_region_result.region.valid,
        },
        {
            "region": "throat",
            "peak_heat_flux_w_m2": result.throat_result.region.peak_heat_flux_w_m2,
            "peak_inner_wall_temp_k": result.throat_result.region.peak_inner_wall_temp_k,
            "allowable_temp_k": result.throat_result.region.max_allowable_temp_k,
            "thermal_margin_k": result.throat_result.region.thermal_margin_k,
            "valid": result.throat_result.region.valid,
        },
        {
            "region": "diverging_nozzle",
            "peak_heat_flux_w_m2": result.diverging_nozzle_result.region.peak_heat_flux_w_m2,
            "peak_inner_wall_temp_k": result.diverging_nozzle_result.region.peak_inner_wall_temp_k,
            "allowable_temp_k": result.diverging_nozzle_result.region.max_allowable_temp_k,
            "thermal_margin_k": result.diverging_nozzle_result.region.thermal_margin_k,
            "valid": result.diverging_nozzle_result.region.valid,
        },
    ]
    if result.prechamber_result is not None:
        base_rows.append(
            {
                "region": "prechamber",
                "peak_heat_flux_w_m2": result.prechamber_result.region.peak_heat_flux_w_m2,
                "peak_inner_wall_temp_k": result.prechamber_result.region.peak_inner_wall_temp_k,
                "allowable_temp_k": result.prechamber_result.region.max_allowable_temp_k,
                "thermal_margin_k": result.prechamber_result.region.thermal_margin_k,
                "valid": result.prechamber_result.region.valid,
            }
        )
    if result.postchamber_result is not None:
        base_rows.append(
            {
                "region": "postchamber",
                "peak_heat_flux_w_m2": result.postchamber_result.region.peak_heat_flux_w_m2,
                "peak_inner_wall_temp_k": result.postchamber_result.region.peak_inner_wall_temp_k,
                "allowable_temp_k": result.postchamber_result.region.max_allowable_temp_k,
                "thermal_margin_k": result.postchamber_result.region.thermal_margin_k,
                "valid": result.postchamber_result.region.valid,
            }
        )
    if result.injector_face_result is not None:
        base_rows.append(
            {
                "region": "injector_face",
                "peak_heat_flux_w_m2": result.injector_face_result.region.peak_heat_flux_w_m2,
                "peak_inner_wall_temp_k": result.injector_face_result.region.peak_inner_wall_temp_k,
                "allowable_temp_k": result.injector_face_result.region.max_allowable_temp_k,
                "thermal_margin_k": result.injector_face_result.region.thermal_margin_k,
                "valid": result.injector_face_result.region.valid,
            }
        )
    canonical_reports = {row["region"]: row for row in result.canonical_region_reports}
    rows: list[dict[str, float | str | bool | None]] = []
    for row in base_rows:
        report = canonical_reports.get(str(row["region"]))
        rows.append(
            {
                **row,
                "h_g_w_m2k": None if report is None else report.get("h_g_w_m2k"),
                "q_doubleprime_g_w_m2": None if report is None else report.get("q_doubleprime_g_w_m2"),
                "T_hot_wall_k": None if report is None else report.get("T_hot_wall_k"),
                "T_liner_shell_interface_k": None if report is None else report.get("T_liner_shell_interface_k"),
                "T_outer_shell_k": None if report is None else report.get("T_outer_shell_k"),
                "remaining_liner_thickness_m": None if report is None else report.get("remaining_liner_thickness_m"),
                "failure_reasons": " | ".join(result.canonical_state.get("diagnostics", {}).get("failure_reasons", []))
                if result.canonical_state
                else "",
            }
        )
    return rows


def _history_rows(result: ThermalSizingResult) -> list[dict[str, float | str]]:
    region_entries = [
        ("chamber", result.chamber_region_result.region),
        ("throat", result.throat_result.region),
        ("diverging_nozzle", result.diverging_nozzle_result.region),
    ]
    if result.prechamber_result is not None:
        region_entries.append(("prechamber", result.prechamber_result.region))
    if result.postchamber_result is not None:
        region_entries.append(("postchamber", result.postchamber_result.region))
    if result.injector_face_result is not None:
        region_entries.append(("injector_face", result.injector_face_result.region))

    rows: list[dict[str, float | str]] = []
    for region_name, region in region_entries:
        for time_s, heat_flux, inner_temp, outer_temp in zip(
            region.time_history_s,
            region.heat_flux_history_w_m2,
            region.inner_wall_temp_history_k,
            region.outer_wall_temp_history_k,
        ):
            rows.append(
                {
                    "region": region_name,
                    "time_s": time_s,
                    "heat_flux_w_m2": heat_flux,
                    "inner_wall_temp_k": inner_temp,
                    "outer_wall_temp_k": outer_temp,
                }
            )
    return rows


def _summary_lines(load_cases: Sequence[ThermalLoadCase], result: ThermalSizingResult) -> list[str]:
    warnings = result.warnings or ["None"]
    failure_reasons = result.canonical_state.get("diagnostics", {}).get("failure_reasons", []) if result.canonical_state else []
    governing_region = min(result.summary_margins, key=result.summary_margins.get)
    return [
        "Thermal Sizing Summary",
        f"Governing thermal load case: {result.governing_load_case.case_name} ({result.governing_load_case.source_stage})",
        f"Load cases considered: {len(load_cases)}",
        f"Chamber material / thickness: {result.chamber_region_result.region.material_name} / {result.chamber_region_result.region.selected_wall_thickness_m * 1000.0:.3f} mm",
        f"Peak chamber heat flux [MW/m^2]: {result.chamber_region_result.region.peak_heat_flux_w_m2 / 1.0e6:.3f}",
        f"Peak chamber inner-wall temperature [K]: {result.chamber_region_result.region.peak_inner_wall_temp_k:.1f}",
        f"Peak throat heat flux [MW/m^2]: {result.throat_result.region.peak_heat_flux_w_m2 / 1.0e6:.3f}",
        f"Peak throat temperature [K]: {result.throat_result.region.peak_inner_wall_temp_k:.1f}",
        f"Injector-face valid: {True if result.injector_face_result is None else result.injector_face_result.region.valid}",
        f"Thermal protection mass estimate [kg]: {result.total_thermal_protection_mass_estimate_kg:.3f}",
        f"Governing region: {governing_region}",
        f"Thermal valid: {result.thermal_valid}",
        "",
        "Failure Reasons:",
        *(failure_reasons or ["None"]),
        "",
        "Warnings:",
        *warnings,
    ]


def write_thermal_outputs(
    output_dir: str | Path,
    *,
    load_cases: Sequence[ThermalLoadCase],
    result: ThermalSizingResult,
) -> Path:
    """Write the standard thermal output bundle."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    region_rows = _region_rows(result)
    history_rows = _history_rows(result)
    write_json(destination / "thermal_load_cases.json", {"load_cases": [item.to_dict() for item in load_cases]})
    write_json(destination / "thermal_sizing.json", result.to_dict())
    write_rows_csv(destination / "thermal_sizing.csv", region_rows)
    write_rows_csv(destination / "thermal_region_histories.csv", history_rows)
    write_rows_csv(
        destination / "thermal_protection_mass.csv",
        [
            {
                "protection_name": item.protection_name,
                "protected_region": item.protected_region,
                "material_name": item.material_name,
                "selected_thickness_mm": item.selected_thickness_m * 1000.0,
                "mass_estimate_kg": item.mass_estimate_kg,
            }
            for item in (result.optional_liner_result, result.optional_throat_insert_result)
            if item is not None
        ],
    )
    write_json(
        destination / "thermal_checks.json",
        {
            "validity_flags": result.validity_flags,
            "summary_margins": result.summary_margins,
            "thermal_valid": result.thermal_valid,
            "warnings": result.warnings,
            "failure_reason": result.failure_reason,
        },
    )
    (destination / "thermal_summary.txt").write_text("\n".join(_summary_lines(load_cases, result)) + "\n", encoding="utf-8")

    region_entries = [
        ("chamber", result.chamber_region_result.region),
        ("throat", result.throat_result.region),
        ("diverging_nozzle", result.diverging_nozzle_result.region),
    ]
    if result.prechamber_result is not None:
        region_entries.append(("prechamber", result.prechamber_result.region))
    if result.postchamber_result is not None:
        region_entries.append(("postchamber", result.postchamber_result.region))
    if result.injector_face_result is not None:
        region_entries.append(("injector_face", result.injector_face_result.region))

    write_line_plot(
        destination / "wall_temperature_vs_time.svg",
        [
            {
                "label": f"{region_name} inner wall [K]",
                "x": region.time_history_s,
                "y": region.inner_wall_temp_history_k,
            }
            for region_name, region in region_entries
        ],
        "Wall Temperature vs Time",
        "Time [s]",
        "Temperature [K]",
    )
    write_line_plot(
        destination / "heat_flux_vs_time.svg",
        [
            {
                "label": f"{region_name} heat flux [MW/m^2]",
                "x": region.time_history_s,
                "y": [value / 1.0e6 for value in region.heat_flux_history_w_m2],
            }
            for region_name, region in region_entries
        ],
        "Heat Flux vs Time",
        "Time [s]",
        "Heat Flux [MW/m^2]",
    )
    write_horizontal_bar_chart(
        destination / "peak_temperature_by_region.svg",
        [{"label": row["region"], "value": row["peak_inner_wall_temp_k"]} for row in region_rows],
        "Peak Inner-Wall Temperature by Region",
        "Temperature [K]",
    )
    write_horizontal_bar_chart(
        destination / "thermal_margin_by_region.svg",
        [{"label": row["region"], "value": row["thermal_margin_k"]} for row in region_rows],
        "Thermal Margin by Region",
        "Margin to limit [K]",
    )
    write_grouped_horizontal_bar_chart(
        destination / "thermal_load_case_comparison.svg",
        [
            {
                "label": case.case_name,
                "values": {
                    "Pc peak [bar]": max(case.chamber_pressure_pa_time) / 1.0e5,
                    "mdot peak [kg/s]": max(case.mdot_total_kg_s_time),
                },
            }
            for case in load_cases
        ],
        ["Pc peak [bar]", "mdot peak [kg/s]"],
        "Thermal Load-Case Comparison",
        "Load metric",
    )
    return destination
