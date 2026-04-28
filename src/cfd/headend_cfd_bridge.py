"""Head-end and grain-entrance CFD-to-reduced-order correction extraction."""

from __future__ import annotations

from src.cfd.cfd_types import CfdCorrectionPackage, CfdResultSummary


HEADEND_CORRECTION_TYPES = {"headend_maldistribution_factor", "local_heat_flux_multiplier"}


def headend_corrections_from_summary(summary: CfdResultSummary) -> list[CfdCorrectionPackage]:
    """Extract head-end correction packages from one CFD summary."""

    packages: list[CfdCorrectionPackage] = []
    explicit = summary.comparison_to_reduced_order.get("corrections", [])
    for correction in explicit:
        correction_type = str(dict(correction).get("correction_type", "")).strip()
        if correction_type not in HEADEND_CORRECTION_TYPES:
            continue
        scalar_value = dict(correction).get("scalar_value")
        if scalar_value is None:
            continue
        correction_data = {"scalar_value": float(scalar_value)}
        if correction_type == "local_heat_flux_multiplier":
            correction_data["region_name"] = str(dict(correction).get("region_name", "injector_face"))
        packages.append(
            CfdCorrectionPackage(
                correction_type=correction_type,
                source_case_id=summary.case_id,
                valid_operating_range=dict(dict(correction).get("valid_operating_range", {})),
                correction_data=correction_data,
                downstream_target_module="thermal" if correction_type == "local_heat_flux_multiplier" else "internal_ballistics",
                notes=["Derived from an ingested CFD result summary.", *summary.notes],
                confidence_level=str(summary.extracted_key_outputs.get("confidence_level", "medium")),
            )
        )
    for correction_type in HEADEND_CORRECTION_TYPES:
        scalar_value = summary.extracted_key_outputs.get(correction_type)
        if scalar_value is None or any(package.correction_type == correction_type for package in packages):
            continue
        correction_data = {"scalar_value": float(scalar_value)}
        if correction_type == "local_heat_flux_multiplier":
            correction_data["region_name"] = "injector_face"
        packages.append(
            CfdCorrectionPackage(
                correction_type=correction_type,
                source_case_id=summary.case_id,
                valid_operating_range=dict(summary.extracted_key_outputs.get("valid_operating_range", {})),
                correction_data=correction_data,
                downstream_target_module="thermal" if correction_type == "local_heat_flux_multiplier" else "internal_ballistics",
                notes=["Derived from a scalar CFD correction field in the ingested summary.", *summary.notes],
                confidence_level=str(summary.extracted_key_outputs.get("confidence_level", "medium")),
            )
        )
    return packages
