"""First-pass CFD target-definition and correction-bridge package."""

from src.cfd.cfd_types import (
    CfdBoundaryConditionPackage,
    CfdCampaignPlan,
    CfdCaseDefinition,
    CfdCorrectionPackage,
    CfdGeometryPackage,
    CfdOperatingPoint,
    CfdResultSummary,
    CfdTargetDefinition,
)
from src.cfd.workflow import merge_cfd_config, run_cfd_workflow

__all__ = [
    "CfdBoundaryConditionPackage",
    "CfdCampaignPlan",
    "CfdCaseDefinition",
    "CfdCorrectionPackage",
    "CfdGeometryPackage",
    "CfdOperatingPoint",
    "CfdResultSummary",
    "CfdTargetDefinition",
    "merge_cfd_config",
    "run_cfd_workflow",
]
