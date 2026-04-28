"""Validity checks for the testing and progression workflow."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.testing.test_types import InstrumentationPlan, ModelVsTestComparison, ProgressionGateResult, TestArticleDefinition, TestDataset, TestStageDefinition


def build_testing_validity_flags(
    testing_config: Mapping[str, Any],
    *,
    stages: Sequence[TestStageDefinition],
    articles: Sequence[TestArticleDefinition],
    instrumentation_plans: Sequence[InstrumentationPlan],
    datasets: Sequence[TestDataset],
    comparisons: Sequence[ModelVsTestComparison],
    gate_results: Sequence[ProgressionGateResult],
) -> dict[str, bool]:
    """Build the top-level validity flags for the testing workflow."""

    thresholds = dict(testing_config.get("progression_thresholds", {}))
    return {
        "stages_defined": bool(stages),
        "articles_defined": bool(articles),
        "instrumentation_defined": bool(instrumentation_plans),
        "progression_thresholds_defined": bool(thresholds),
        "datasets_valid_or_absent": all(all(item.validity_flags.values()) for item in datasets) if datasets else True,
        "comparisons_valid_or_absent": all(all(item.validity_flags.values()) for item in comparisons) if comparisons else True,
        "gates_defined": bool(gate_results) or bool(stages),
    }


def collect_testing_warnings(
    *,
    datasets: Sequence[TestDataset],
    calibration_warnings: Sequence[str],
) -> list[str]:
    """Collect user-visible warnings for the testing workflow."""

    warnings: list[str] = []
    for dataset in datasets:
        if not all(dataset.validity_flags.values()):
            warnings.append(f"Dataset {dataset.run_id} is missing one or more required channels for its article plan.")
    warnings.extend(str(item) for item in calibration_warnings)
    return warnings
