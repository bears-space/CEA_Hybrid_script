"""Generation and application of CFD-derived correction packages."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from src.cfd.cfd_types import CfdCorrectionPackage, CfdResultSummary, CfdTargetDefinition
from src.cfd.headend_cfd_bridge import headend_corrections_from_summary
from src.cfd.injector_cfd_bridge import injector_corrections_from_summary
from src.cfd.nozzle_cfd_bridge import nozzle_corrections_from_summary


def template_correction_packages_for_targets(targets: Sequence[CfdTargetDefinition]) -> list[CfdCorrectionPackage]:
    """Return placeholder correction packages for the planned CFD targets."""

    packages: list[CfdCorrectionPackage] = []
    for target in targets:
        if target.target_category == "injector_plenum":
            templates = [
                ("injector_cda_multiplier", "hydraulic_validation", "Scalar injector CdA multiplier."),
                ("injector_distribution_factor", "internal_ballistics", "Ring-wise or axial distribution factor."),
            ]
        elif target.target_category == "headend_prechamber":
            templates = [
                ("headend_maldistribution_factor", "internal_ballistics", "Head-end oxidizer loading factor."),
                ("local_heat_flux_multiplier", "thermal", "Injector-face or grain-entrance heat-flux multiplier."),
            ]
        elif target.target_category == "nozzle_local":
            templates = [
                ("nozzle_loss_factor", "nozzle_offdesign", "Nozzle discharge or performance loss factor."),
                ("separation_penalty_factor", "nozzle_offdesign", "Off-design separation penalty factor."),
                ("local_heat_flux_multiplier", "thermal", "Throat or divergence heat-flux multiplier."),
            ]
        else:
            templates = [
                ("regression_correction_map", "internal_ballistics", "Reacting-flow regression or loading correction map placeholder."),
            ]
        for correction_type, module, note in templates:
            packages.append(
                CfdCorrectionPackage(
                    correction_type=correction_type,
                    source_case_id=f"template:{target.target_name}",
                    valid_operating_range={},
                    correction_data={"template": True, "expected_input": note},
                    downstream_target_module=module,
                    notes=[f"Template package generated from planned target '{target.target_name}'."],
                    confidence_level="template",
                )
            )
    return packages


def correction_packages_from_results(result_summaries: Iterable[CfdResultSummary]) -> list[CfdCorrectionPackage]:
    """Convert summarized CFD results into reusable correction packages."""

    packages: list[CfdCorrectionPackage] = []
    for summary in result_summaries:
        packages.extend(injector_corrections_from_summary(summary))
        packages.extend(headend_corrections_from_summary(summary))
        packages.extend(nozzle_corrections_from_summary(summary))
    deduped: list[CfdCorrectionPackage] = []
    seen: set[tuple[str, str, str]] = set()
    for package in packages:
        key = (package.correction_type, package.source_case_id, package.downstream_target_module)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(package)
    return deduped


def filter_correction_packages(
    correction_packages: Sequence[CfdCorrectionPackage],
    corrections_source: str,
) -> list[CfdCorrectionPackage]:
    """Filter correction packages by the configured application mode."""

    source_mode = str(corrections_source).lower()
    if source_mode in {"combined", "all"}:
        return list(correction_packages)
    if source_mode == "none":
        return []
    if source_mode == "injector_only":
        return [
            package
            for package in correction_packages
            if package.correction_type in {"injector_cda_multiplier", "injector_distribution_factor"}
        ]
    if source_mode == "headend_only":
        return [
            package
            for package in correction_packages
            if package.correction_type in {"headend_maldistribution_factor", "local_heat_flux_multiplier"}
            and package.downstream_target_module in {"internal_ballistics", "thermal"}
        ]
    if source_mode == "nozzle_only":
        return [
            package
            for package in correction_packages
            if package.correction_type in {"nozzle_loss_factor", "separation_penalty_factor", "local_heat_flux_multiplier"}
            and package.downstream_target_module in {"nozzle_offdesign", "thermal"}
        ]
    return list(correction_packages)


def _scalar_value(package: CfdCorrectionPackage) -> float | None:
    value = package.correction_data.get("scalar_value")
    if value is None:
        return None
    return float(value)


def apply_correction_packages_to_config(
    study_config: Mapping[str, Any],
    correction_packages: Sequence[CfdCorrectionPackage],
) -> dict[str, Any]:
    """Apply supported CFD correction packages to a copied workflow config."""

    updated = deepcopy(dict(study_config))
    for package in correction_packages:
        scalar_value = _scalar_value(package)
        if scalar_value is None or scalar_value <= 0.0:
            continue
        if package.correction_type == "injector_cda_multiplier":
            updated["nominal"]["blowdown"]["injector"]["cd"] = (
                float(updated["nominal"]["blowdown"]["injector"]["cd"]) * scalar_value
            )
            updated["injector_design"]["default_injector_cd"] = (
                float(updated["injector_design"]["default_injector_cd"]) * scalar_value
            )
        elif package.correction_type in {"injector_distribution_factor", "headend_maldistribution_factor"}:
            updated["internal_ballistics"]["axial_correction_mode"] = "showerhead_head_end_bias"
            updated["internal_ballistics"]["axial_head_end_bias_strength"] = (
                float(updated["internal_ballistics"]["axial_head_end_bias_strength"]) * scalar_value
            )
        elif package.correction_type == "local_heat_flux_multiplier":
            region_name = str(package.correction_data.get("region_name", "throat")).lower()
            if region_name in {"injector_face", "headend", "grain_entrance"}:
                updated["thermal"]["design_policy"]["injector_face_htc_multiplier"] = (
                    float(updated["thermal"]["design_policy"]["injector_face_htc_multiplier"]) * scalar_value
                )
            else:
                updated["thermal"]["design_policy"]["throat_htc_multiplier"] = (
                    float(updated["thermal"]["design_policy"]["throat_htc_multiplier"]) * scalar_value
                )
        elif package.correction_type == "nozzle_loss_factor":
            updated["nominal"]["loss_factors"]["nozzle_discharge_factor"] = (
                float(updated["nominal"]["loss_factors"]["nozzle_discharge_factor"]) * scalar_value
            )
        elif package.correction_type == "separation_penalty_factor":
            risk_level = str(package.correction_data.get("risk_level", "")).lower()
            if risk_level == "high":
                updated["nozzle_offdesign"]["penalties"]["high_risk_cf_multiplier"] = (
                    float(updated["nozzle_offdesign"]["penalties"]["high_risk_cf_multiplier"]) * scalar_value
                )
            elif risk_level == "moderate":
                updated["nozzle_offdesign"]["penalties"]["moderate_risk_cf_multiplier"] = (
                    float(updated["nozzle_offdesign"]["penalties"]["moderate_risk_cf_multiplier"]) * scalar_value
                )
            else:
                updated["nozzle_offdesign"]["penalties"]["moderate_risk_cf_multiplier"] = (
                    float(updated["nozzle_offdesign"]["penalties"]["moderate_risk_cf_multiplier"]) * scalar_value
                )
                updated["nozzle_offdesign"]["penalties"]["high_risk_cf_multiplier"] = (
                    float(updated["nozzle_offdesign"]["penalties"]["high_risk_cf_multiplier"]) * scalar_value
                )
    return updated


def correction_comparison_rows(
    study_config: Mapping[str, Any],
    updated_config: Mapping[str, Any],
    correction_packages: Sequence[CfdCorrectionPackage],
) -> list[dict[str, Any]]:
    """Build a reduced-order before/after comparison table for applied CFD corrections."""

    rows: list[dict[str, Any]] = []
    base = dict(study_config)
    updated = dict(updated_config)
    for package in correction_packages:
        scalar_value = _scalar_value(package)
        if scalar_value is None:
            continue
        if package.correction_type == "injector_cda_multiplier":
            rows.append(
                {
                    "parameter": "nominal.blowdown.injector.cd",
                    "base_value": float(base["nominal"]["blowdown"]["injector"]["cd"]),
                    "corrected_value": float(updated["nominal"]["blowdown"]["injector"]["cd"]),
                    "correction_type": package.correction_type,
                    "source_case_id": package.source_case_id,
                    "downstream_target_module": package.downstream_target_module,
                }
            )
        elif package.correction_type in {"injector_distribution_factor", "headend_maldistribution_factor"}:
            rows.append(
                {
                    "parameter": "internal_ballistics.axial_head_end_bias_strength",
                    "base_value": float(base["internal_ballistics"]["axial_head_end_bias_strength"]),
                    "corrected_value": float(updated["internal_ballistics"]["axial_head_end_bias_strength"]),
                    "correction_type": package.correction_type,
                    "source_case_id": package.source_case_id,
                    "downstream_target_module": package.downstream_target_module,
                }
            )
        elif package.correction_type == "local_heat_flux_multiplier":
            region_name = str(package.correction_data.get("region_name", "throat")).lower()
            parameter = (
                "thermal.design_policy.injector_face_htc_multiplier"
                if region_name in {"injector_face", "headend", "grain_entrance"}
                else "thermal.design_policy.throat_htc_multiplier"
            )
            base_value = (
                float(base["thermal"]["design_policy"]["injector_face_htc_multiplier"])
                if "injector_face" in parameter
                else float(base["thermal"]["design_policy"]["throat_htc_multiplier"])
            )
            corrected_value = (
                float(updated["thermal"]["design_policy"]["injector_face_htc_multiplier"])
                if "injector_face" in parameter
                else float(updated["thermal"]["design_policy"]["throat_htc_multiplier"])
            )
            rows.append(
                {
                    "parameter": parameter,
                    "base_value": base_value,
                    "corrected_value": corrected_value,
                    "correction_type": package.correction_type,
                    "source_case_id": package.source_case_id,
                    "downstream_target_module": package.downstream_target_module,
                }
            )
        elif package.correction_type == "nozzle_loss_factor":
            rows.append(
                {
                    "parameter": "nominal.loss_factors.nozzle_discharge_factor",
                    "base_value": float(base["nominal"]["loss_factors"]["nozzle_discharge_factor"]),
                    "corrected_value": float(updated["nominal"]["loss_factors"]["nozzle_discharge_factor"]),
                    "correction_type": package.correction_type,
                    "source_case_id": package.source_case_id,
                    "downstream_target_module": package.downstream_target_module,
                }
            )
        elif package.correction_type == "separation_penalty_factor":
            rows.append(
                {
                    "parameter": "nozzle_offdesign.penalties",
                    "base_value": min(
                        float(base["nozzle_offdesign"]["penalties"]["moderate_risk_cf_multiplier"]),
                        float(base["nozzle_offdesign"]["penalties"]["high_risk_cf_multiplier"]),
                    ),
                    "corrected_value": min(
                        float(updated["nozzle_offdesign"]["penalties"]["moderate_risk_cf_multiplier"]),
                        float(updated["nozzle_offdesign"]["penalties"]["high_risk_cf_multiplier"]),
                    ),
                    "correction_type": package.correction_type,
                    "source_case_id": package.source_case_id,
                    "downstream_target_module": package.downstream_target_module,
                }
            )
    return rows
