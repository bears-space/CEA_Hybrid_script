"""JSON-backed shared constants and option keys for the blowdown model."""

from __future__ import annotations

from project_data import load_project_constants


_BLOWDOWN_CONSTANTS = load_project_constants()["blowdown"]
_PHYSICS = _BLOWDOWN_CONSTANTS["physics"]
_UI_MODES = _BLOWDOWN_CONSTANTS["ui_modes"]
_DELTA_P_MODES = _BLOWDOWN_CONSTANTS["injector_delta_p_modes"]
_REGRESSION_PRESETS = _BLOWDOWN_CONSTANTS["regression_presets"]
_PRESSURE_DROP_POLICIES = _BLOWDOWN_CONSTANTS["injector_pressure_drop_policies"]

G0_MPS2 = float(_PHYSICS["g0_mps2"])
NITROUS_OXIDE_FLUID = _PHYSICS["nitrous_oxide_fluid"]
N2O_T_MIN_K = float(_PHYSICS["n2o_temperature_limits_k"]["min"])
N2O_T_MAX_K = float(_PHYSICS["n2o_temperature_limits_k"]["max"])

SEED_CASE_HIGHEST_ISP = _BLOWDOWN_CONSTANTS["seed_case"]["highest_isp"]

UI_MODE_BASIC = _UI_MODES["basic"]
UI_MODE_ADVANCED = _UI_MODES["advanced"]

INJECTOR_DELTA_P_MODE_EXPLICIT = _DELTA_P_MODES["explicit"]
INJECTOR_DELTA_P_MODE_FRACTION_OF_PC = _DELTA_P_MODES["fraction_of_pc"]

REGRESSION_PRESET_CUSTOM = _REGRESSION_PRESETS["custom"]["key"]
REGRESSION_PRESET_PROJECT_DEFAULT = _REGRESSION_PRESETS["project_default_paraffin_abs"]["key"]
REGRESSION_PRESET_OPTIONS = {
    payload["key"]: {
        "label": payload["label"],
        "a_reg_si": payload["a_reg_si"],
        "n_reg": payload["n_reg"],
    }
    for payload in _REGRESSION_PRESETS.values()
}

INJECTOR_PRESSURE_DROP_POLICY_LOW = _PRESSURE_DROP_POLICIES["low"]["key"]
INJECTOR_PRESSURE_DROP_POLICY_NOMINAL = _PRESSURE_DROP_POLICIES["nominal"]["key"]
INJECTOR_PRESSURE_DROP_POLICY_CONSERVATIVE = _PRESSURE_DROP_POLICIES["conservative"]["key"]
INJECTOR_PRESSURE_DROP_POLICY_OPTIONS = {
    payload["key"]: {
        "label": payload["label"],
        "delta_p_fraction_of_pc": payload["delta_p_fraction_of_pc"],
    }
    for payload in _PRESSURE_DROP_POLICIES.values()
}

STOP_REASON_LABELS = dict(_BLOWDOWN_CONSTANTS["stop_reason_labels"])
ESTIMATION_BASIS_NOTES = list(_BLOWDOWN_CONSTANTS["estimation_basis_notes"])
MODEL_ASSUMPTIONS = list(_BLOWDOWN_CONSTANTS["model_assumptions"])
