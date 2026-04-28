"""Canonical engine state and deterministic geometry sizing helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import math
from typing import Any, Mapping

from src.blowdown_hybrid.first_pass import blend_density_from_volume_fraction
from src.sizing.nozzle_profile import build_conical_nozzle_contour
def _round_up_to_increment(value_m: float, increment_m: float) -> float:
    if increment_m <= 0.0:
        return float(value_m)
    return math.ceil(float(value_m) / float(increment_m)) * float(increment_m)


def _structural_material_catalog() -> dict[str, dict[str, float]]:
    return {
        "aluminum_6061_t6": {"yield_strength_pa": 276.0e6},
        "aluminum_7075_t6": {"yield_strength_pa": 505.0e6},
        "stainless_304": {"yield_strength_pa": 215.0e6},
        "steel_4140_qt": {"yield_strength_pa": 655.0e6},
        "titanium_6al4v": {"yield_strength_pa": 880.0e6},
    }


def _thermal_material_catalog() -> dict[str, dict[str, float]]:
    return {
        "aluminum_6061_t6": {"conductivity_w_mk": 167.0, "density_kg_m3": 2700.0},
        "aluminum_7075_t6": {"conductivity_w_mk": 130.0, "density_kg_m3": 2810.0},
        "stainless_304": {"conductivity_w_mk": 16.2, "density_kg_m3": 8000.0},
        "steel_4140_qt": {"conductivity_w_mk": 42.0, "density_kg_m3": 7850.0},
        "titanium_6al4v": {"conductivity_w_mk": 6.7, "density_kg_m3": 4430.0},
        "phenolic_liner": {"conductivity_w_mk": 0.25, "density_kg_m3": 1350.0},
        "graphite": {"conductivity_w_mk": 90.0, "density_kg_m3": 1750.0},
    }


def _allowable_stress_pa(material_name: str, structural_policy: Mapping[str, Any]) -> float:
    material = _structural_material_catalog()[str(material_name)]
    allowable_basis = str(structural_policy["allowable_basis"]).lower()
    if allowable_basis == "ultimate_based":
        return float(material["yield_strength_pa"]) / max(float(structural_policy["ultimate_safety_factor"]), 1.0)
    return float(material["yield_strength_pa"]) / max(float(structural_policy["yield_safety_factor"]), 1.0)


def _structural_policy_from_config(structural_config: Mapping[str, Any]) -> dict[str, Any]:
    policy = dict(structural_config.get("design_policy", {}))
    return {
        "allowable_basis": str(structural_config.get("allowable_basis", "yield_based")),
        "yield_safety_factor": float(policy["yield_safety_factor"]),
        "ultimate_safety_factor": float(policy["ultimate_safety_factor"]),
        "thin_wall_switch_ratio": float(policy["thin_wall_switch_ratio"]),
        "minimum_wall_thickness_m": float(policy["minimum_wall_thickness_m"]),
        "thickness_roundup_increment_m": float(policy["thickness_roundup_increment_m"]),
        "corrosion_or_manufacturing_allowance_m": float(policy["corrosion_or_manufacturing_allowance_m"]),
    }


def _thermal_policy_from_config(thermal_config: Mapping[str, Any], outer_ambient_temp_k: float) -> dict[str, Any]:
    policy = dict(thermal_config.get("design_policy", {}))
    return {
        "outer_h_guess_w_m2k": float(policy["outer_h_guess_w_m2k"]),
        "outer_ambient_temp_k": float(policy.get("outer_ambient_temp_k", outer_ambient_temp_k)),
        "minimum_protection_thickness_m": float(policy["minimum_protection_thickness_m"]),
    }


@dataclass(frozen=True)
class EngineMaterials:
    """Canonical engine material selection."""

    shell_material: str
    liner_material: str
    injector_material: str
    closure_material: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EngineGeometry:
    """Canonical geometry state in SI units."""

    shell_inner_radius_m: float
    shell_thickness_m: float
    liner_thickness_m: float
    shell_outer_radius_m: float
    hot_gas_radius_m: float
    grain_outer_radius_m: float
    grain_port_radius_initial_m: float
    grain_port_radius_final_m: float
    grain_length_m: float
    radial_clearance_m: float
    prechamber_length_m: float
    postchamber_length_m: float
    chamber_total_length_m: float
    throat_radius_m: float
    exit_radius_m: float
    nozzle_converging_length_m: float
    nozzle_diverging_length_m: float
    nozzle_total_length_m: float
    injector_hole_diameter_m: float
    injector_hole_count: int
    injector_total_hole_area_m2: float
    initial_web_thickness_m: float
    final_web_thickness_m: float
    grain_slenderness: float
    web_slenderness: float
    lstar_initial_m: float
    area_expansion_ratio: float
    converging_half_angle_deg: float
    diverging_half_angle_deg: float
    throat_blend_radius_m: float
    hot_gas_free_volume_initial_m3: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnginePerformance:
    """Canonical performance quantities reused by later modules."""

    chamber_pressure_pa: float
    ox_mass_flow_kg_s: float
    fuel_mass_required_kg: float
    burn_time_s: float
    injector_delta_p_pa: float
    loaded_fuel_mass_kg: float
    remaining_fuel_mass_kg: float
    fuel_density_kg_m3: float
    cstar_mps: float
    target_thrust_n: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EngineConstraints:
    """Hard packaging and validity constraints."""

    max_shell_outer_diameter_m: float
    max_hot_gas_diameter_m: float
    max_grain_length_m: float
    max_total_chamber_length_m: float
    max_nozzle_length_m: float
    max_exit_diameter_m: float
    min_initial_web_m: float
    min_final_web_m: float
    max_grain_slenderness: float
    max_web_slenderness: float
    min_lstar_m: float
    max_lstar_m: float
    max_area_expansion_ratio: float
    alpha_min_deg: float
    alpha_max_deg: float
    beta_min_deg: float
    beta_max_deg: float
    epsilon_min: float
    epsilon_max: float
    maximum_shell_inner_wall_temp_k: float
    minimum_remaining_liner_thickness_m: float
    use_ablative_liner_model: bool
    rho_liner: float
    H_ablation_effective: float
    T_pyrolysis_k: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EngineValidity:
    """Hard validity flags shared across modules."""

    geometry_valid: bool
    structural_valid: bool
    thermal_valid: bool
    injector_valid: bool
    overall_valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EngineDiagnostics:
    """Warnings, failures, and solver decisions."""

    warnings: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    solver_report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EngineState:
    """Single source of truth shared by geometry, structural, and thermal layers."""

    materials: EngineMaterials
    geometry: EngineGeometry
    performance: EnginePerformance
    constraints: EngineConstraints
    validity: EngineValidity
    diagnostics: EngineDiagnostics
    thermal: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "EngineState":
        return cls(
            materials=EngineMaterials(**dict(payload["materials"])),
            geometry=EngineGeometry(**dict(payload["geometry"])),
            performance=EnginePerformance(**dict(payload["performance"])),
            constraints=EngineConstraints(**dict(payload["constraints"])),
            validity=EngineValidity(**dict(payload["validity"])),
            diagnostics=EngineDiagnostics(**dict(payload["diagnostics"])),
            thermal=dict(payload.get("thermal", {})),
        )


def shell_outer_radius_m(shell_inner_radius_m: float, shell_thickness_m: float) -> float:
    return float(shell_inner_radius_m) + float(shell_thickness_m)


def hot_gas_radius_m(shell_inner_radius_m: float, liner_thickness_m: float) -> float:
    return float(shell_inner_radius_m) - float(liner_thickness_m)


def grain_outer_radius_m(hot_radius_m: float, radial_clearance_m: float) -> float:
    return float(hot_radius_m) - float(radial_clearance_m)


def grain_port_radius_from_fuel_mass(
    *,
    fuel_mass_kg: float,
    fuel_density_kg_m3: float,
    grain_length_m: float,
    grain_outer_radius_m: float,
) -> float:
    if fuel_density_kg_m3 <= 0.0 or grain_length_m <= 0.0:
        return 0.0
    term = float(grain_outer_radius_m) ** 2 - float(fuel_mass_kg) / (
        float(fuel_density_kg_m3) * math.pi * float(grain_length_m)
    )
    return math.sqrt(max(term, 0.0))


def web_thickness_m(grain_outer_radius_m: float, grain_port_radius_m: float) -> float:
    return float(grain_outer_radius_m) - float(grain_port_radius_m)


def grain_slenderness(grain_length_m: float, grain_outer_radius_m: float) -> float:
    return float(grain_length_m) / max(2.0 * float(grain_outer_radius_m), 1.0e-12)


def web_slenderness(grain_length_m: float, initial_web_thickness_m: float) -> float:
    return float(grain_length_m) / max(2.0 * float(initial_web_thickness_m), 1.0e-12)


def throat_area_m2(throat_radius_m: float) -> float:
    return math.pi * float(throat_radius_m) ** 2


def exit_area_m2(exit_radius_m: float) -> float:
    return math.pi * float(exit_radius_m) ** 2


def injector_single_hole_area_m2(hole_diameter_m: float) -> float:
    return math.pi * float(hole_diameter_m) ** 2 / 4.0


def injector_required_total_area_m2(
    *,
    ox_mass_flow_kg_s: float,
    discharge_coefficient: float,
    oxidizer_density_kg_m3: float,
    injector_delta_p_pa: float,
) -> float:
    if discharge_coefficient <= 0.0 or oxidizer_density_kg_m3 <= 0.0 or injector_delta_p_pa <= 0.0:
        return 0.0
    return float(ox_mass_flow_kg_s) / (
        float(discharge_coefficient) * math.sqrt(2.0 * float(oxidizer_density_kg_m3) * float(injector_delta_p_pa))
    )


def injector_hole_count_from_required_area(required_area_m2: float, hole_diameter_m: float) -> int:
    area_per_hole_m2 = injector_single_hole_area_m2(hole_diameter_m)
    if area_per_hole_m2 <= 0.0:
        return 0
    return max(int(math.ceil(float(required_area_m2) / area_per_hole_m2)), 1)


def injector_actual_total_area_m2(hole_count: int, hole_diameter_m: float) -> float:
    return int(hole_count) * injector_single_hole_area_m2(hole_diameter_m)


def chamber_free_volume_initial_m3(
    *,
    hot_gas_radius_m: float,
    prechamber_length_m: float,
    grain_length_m: float,
    grain_port_radius_initial_m: float,
    postchamber_length_m: float,
) -> float:
    v_pre = math.pi * float(hot_gas_radius_m) ** 2 * float(prechamber_length_m)
    v_port = math.pi * float(grain_port_radius_initial_m) ** 2 * float(grain_length_m)
    v_post = math.pi * float(hot_gas_radius_m) ** 2 * float(postchamber_length_m)
    return v_pre + v_port + v_post


def lstar_initial_m(
    *,
    free_volume_initial_m3: float,
    throat_radius_m: float,
) -> float:
    return float(free_volume_initial_m3) / max(throat_area_m2(throat_radius_m), 1.0e-12)


def thin_wall_required_thickness_m(
    *,
    chamber_pressure_pa: float,
    shell_inner_radius_m: float,
    allowable_stress_pa: float,
) -> float:
    return float(chamber_pressure_pa) * float(shell_inner_radius_m) / max(float(allowable_stress_pa), 1.0e-12)


def selected_shell_thickness_m(
    *,
    chamber_pressure_pa: float,
    shell_inner_radius_m: float,
    allowable_stress_pa: float,
    minimum_wall_thickness_m: float,
    corrosion_allowance_m: float,
    thickness_roundup_increment_m: float,
) -> float:
    required_m = thin_wall_required_thickness_m(
        chamber_pressure_pa=chamber_pressure_pa,
        shell_inner_radius_m=shell_inner_radius_m,
        allowable_stress_pa=allowable_stress_pa,
    )
    selected_minimum_m = max(
        float(minimum_wall_thickness_m),
        float(required_m) + float(corrosion_allowance_m),
    )
    return _round_up_to_increment(selected_minimum_m, thickness_roundup_increment_m)


def thermal_resistance_region_report(
    *,
    region: str,
    time_s: list[float],
    gas_temperature_k_time: list[float],
    gas_side_htc_w_m2k_time: list[float],
    hot_gas_radius_m: float,
    liner_thickness_m: float,
    shell_thickness_m: float,
    length_m: float,
    liner_conductivity_w_mk: float,
    shell_conductivity_w_mk: float,
    outer_h_w_m2k: float,
    ambient_temp_k: float,
    use_ablative_liner_model: bool,
    rho_liner: float,
    H_ablation_effective: float,
    T_pyrolysis_k: float,
) -> dict[str, Any]:
    remaining_liner_thickness_m = max(float(liner_thickness_m), 0.0)
    rows: list[dict[str, Any]] = []

    if not time_s:
        time_s = [0.0]
    if not gas_temperature_k_time:
        gas_temperature_k_time = [ambient_temp_k]
    if not gas_side_htc_w_m2k_time:
        gas_side_htc_w_m2k_time = [outer_h_w_m2k]

    history_len = min(len(time_s), len(gas_temperature_k_time), len(gas_side_htc_w_m2k_time))
    if history_len <= 0:
        time_s = [0.0]
        gas_temperature_k_time = [ambient_temp_k]
        gas_side_htc_w_m2k_time = [outer_h_w_m2k]
        history_len = 1

    for index in range(history_len):
        current_time_s = float(time_s[index])
        gas_temperature_k = float(gas_temperature_k_time[index])
        gas_side_htc_w_m2k = max(float(gas_side_htc_w_m2k_time[index]), 1.0e-9)
        r0 = max(float(hot_gas_radius_m), 1.0e-9)
        r1 = r0 + max(remaining_liner_thickness_m, 0.0)
        r2 = r1 + max(float(shell_thickness_m), 1.0e-9)
        effective_length_m = max(float(length_m), 1.0e-9)
        r_conv_g = 1.0 / (gas_side_htc_w_m2k * 2.0 * math.pi * r0 * effective_length_m)
        r_cond_l = 0.0
        if remaining_liner_thickness_m > 0.0 and liner_conductivity_w_mk > 0.0:
            r_cond_l = math.log(r1 / r0) / (2.0 * math.pi * liner_conductivity_w_mk * effective_length_m)
        r_cond_s = math.log(r2 / r1) / (2.0 * math.pi * shell_conductivity_w_mk * effective_length_m)
        r_conv_o = 1.0 / (max(float(outer_h_w_m2k), 1.0e-9) * 2.0 * math.pi * r2 * effective_length_m)
        r_total = r_conv_g + r_cond_l + r_cond_s + r_conv_o
        q_prime_w = (gas_temperature_k - float(ambient_temp_k)) / max(r_total, 1.0e-12)
        q_doubleprime_g_w_m2 = q_prime_w / (2.0 * math.pi * r0 * effective_length_m)
        hot_wall_temp_k = gas_temperature_k - q_prime_w * r_conv_g
        liner_interface_temp_k = hot_wall_temp_k - q_prime_w * r_cond_l
        outer_shell_temp_k = liner_interface_temp_k - q_prime_w * r_cond_s

        if use_ablative_liner_model and remaining_liner_thickness_m > 0.0 and hot_wall_temp_k > float(T_pyrolysis_k):
            hot_face_temp_k = float(T_pyrolysis_k)
            q_cond_into_structure_w_m2 = 0.0
            if liner_conductivity_w_mk > 0.0 and r1 > r0:
                q_cond_into_structure_w_m2 = liner_conductivity_w_mk * (
                    float(T_pyrolysis_k) - liner_interface_temp_k
                ) / max(r0 * math.log(r1 / r0), 1.0e-12)
            q_excess_w_m2 = max(0.0, q_doubleprime_g_w_m2 - q_cond_into_structure_w_m2)
            s_dot_m_s = q_excess_w_m2 / max(float(rho_liner) * float(H_ablation_effective), 1.0e-12)
            dt_s = 0.0 if index == 0 else max(float(time_s[index]) - float(time_s[index - 1]), 0.0)
            remaining_liner_thickness_m = max(0.0, remaining_liner_thickness_m - s_dot_m_s * dt_s)
            hot_wall_temp_k = hot_face_temp_k

        rows.append(
            {
                "region": region,
                "time_s": current_time_s,
                "h_g_w_m2k": gas_side_htc_w_m2k,
                "q_doubleprime_g_w_m2": q_doubleprime_g_w_m2,
                "T_hot_wall_k": hot_wall_temp_k,
                "T_liner_shell_interface_k": liner_interface_temp_k,
                "T_outer_shell_k": outer_shell_temp_k,
                "remaining_liner_thickness_m": remaining_liner_thickness_m,
            }
        )

    peak_row = dict(max(rows, key=lambda row: row["T_liner_shell_interface_k"]))
    peak_row["history"] = [dict(row) for row in rows]
    peak_row["peak_shell_inner_wall_temp_k"] = peak_row["T_liner_shell_interface_k"]
    peak_row["peak_shell_outer_wall_temp_k"] = peak_row["T_outer_shell_k"]
    return peak_row


def _candidate_section_length_m(
    *,
    mode: str,
    hot_gas_diameter_m: float,
    k_value: float,
    minimum_m: float,
    maximum_m: float,
) -> float:
    if str(mode).lower() == "fixed_length":
        return min(max(float(k_value), float(minimum_m)), float(maximum_m))
    length_m = float(k_value) * float(hot_gas_diameter_m)
    return min(max(length_m, float(minimum_m)), float(maximum_m))


def _fuel_density_kg_m3(study_config: Mapping[str, Any]) -> float:
    grain = study_config["nominal"]["blowdown"]["grain"]
    abs_fraction = float(study_config["nominal"]["performance"]["abs_volume_fraction"])
    return blend_density_from_volume_fraction(
        abs_fraction,
        float(grain["abs_density_kg_m3"]),
        float(grain["paraffin_density_kg_m3"]),
    )


def _constraints_from_config(study_config: Mapping[str, Any]) -> EngineConstraints:
    geometry_policy = dict(study_config["geometry_policy"])
    thermal = dict(study_config["thermal"])
    return EngineConstraints(
        max_shell_outer_diameter_m=float(geometry_policy["max_shell_outer_diameter_m"]),
        max_hot_gas_diameter_m=float(geometry_policy["max_hot_gas_diameter_m"]),
        max_grain_length_m=float(geometry_policy["max_grain_length_m"]),
        max_total_chamber_length_m=float(geometry_policy["max_total_chamber_length_m"]),
        max_nozzle_length_m=float(geometry_policy["max_nozzle_length_m"]),
        max_exit_diameter_m=float(geometry_policy["max_exit_diameter_m"]),
        min_initial_web_m=float(geometry_policy["min_initial_web_m"]),
        min_final_web_m=float(geometry_policy["min_final_web_m"]),
        max_grain_slenderness=float(geometry_policy["max_grain_slenderness"]),
        max_web_slenderness=float(geometry_policy["max_web_slenderness"]),
        min_lstar_m=float(geometry_policy["min_lstar_m"]),
        max_lstar_m=float(geometry_policy["max_lstar_m"]),
        max_area_expansion_ratio=float(geometry_policy["max_area_expansion_ratio"]),
        alpha_min_deg=float(geometry_policy["alpha_min_deg"]),
        alpha_max_deg=float(geometry_policy["alpha_max_deg"]),
        beta_min_deg=float(geometry_policy["beta_min_deg"]),
        beta_max_deg=float(geometry_policy["beta_max_deg"]),
        epsilon_min=float(geometry_policy["epsilon_min"]),
        epsilon_max=float(geometry_policy["epsilon_max"]),
        maximum_shell_inner_wall_temp_k=float(thermal["maximum_shell_inner_wall_temp_k"]),
        minimum_remaining_liner_thickness_m=float(thermal["minimum_remaining_liner_thickness_m"]),
        use_ablative_liner_model=bool(thermal["use_ablative_liner_model"]),
        rho_liner=float(thermal["rho_liner"]),
        H_ablation_effective=float(thermal["H_ablation_effective"]),
        T_pyrolysis_k=float(thermal["T_pyrolysis_k"]),
    )


def _materials_from_config(study_config: Mapping[str, Any]) -> EngineMaterials:
    structural = dict(study_config["structural"])
    thermal = dict(study_config["thermal"])
    structural_materials = dict(structural["component_materials"])
    thermal_materials = dict(thermal["component_materials"])
    return EngineMaterials(
        shell_material=str(structural_materials["chamber_wall"]),
        liner_material=str(thermal_materials["liner"]),
        injector_material=str(structural_materials["injector_plate"]),
        closure_material=str(structural_materials["forward_closure"]),
    )


def _performance_from_nominal(study_config: Mapping[str, Any], nominal_payload: Mapping[str, Any]) -> EnginePerformance:
    runtime = nominal_payload["result"]["runtime"]
    derived = runtime["derived"]
    fuel_required_kg = float(derived["required_fuel_mass_kg"])
    fuel_loaded_kg = float(derived.get("loaded_fuel_mass_kg", fuel_required_kg))
    return EnginePerformance(
        chamber_pressure_pa=float(derived["target_pc_bar"]) * 1.0e5,
        ox_mass_flow_kg_s=float(derived["target_mdot_ox_kg_s"]),
        fuel_mass_required_kg=fuel_required_kg,
        burn_time_s=float(
            nominal_payload.get("metrics", {}).get("burn_time_actual_s")
            or study_config["nominal"]["blowdown"]["simulation"]["burn_time_s"]
        ),
        injector_delta_p_pa=float(derived.get("design_injector_delta_p_bar", derived["injector_delta_p_bar"])) * 1.0e5,
        loaded_fuel_mass_kg=fuel_loaded_kg,
        remaining_fuel_mass_kg=max(fuel_loaded_kg - fuel_required_kg, 0.0),
        fuel_density_kg_m3=_fuel_density_kg_m3(study_config),
        cstar_mps=float(derived.get("cstar_mps", study_config["nominal"]["performance"]["cstar_mps"])),
        target_thrust_n=float(study_config["nominal"]["performance"]["target_thrust_n"]),
    )


def _liner_thickness_m(study_config: Mapping[str, Any], thermal_policy: Mapping[str, Any]) -> float:
    liner_settings = dict(study_config["thermal"].get("liner", {}))
    if liner_settings.get("selected_thickness_m") is not None:
        return float(liner_settings["selected_thickness_m"])
    if bool(liner_settings.get("enabled")):
        return float(thermal_policy["minimum_protection_thickness_m"])
    return 0.0


def _build_failure_checks(
    *,
    geometry: EngineGeometry,
    constraints: EngineConstraints,
) -> list[str]:
    failures: list[str] = []
    shell_outer_diameter_m = 2.0 * float(geometry.shell_outer_radius_m)
    hot_gas_diameter_m = 2.0 * float(geometry.hot_gas_radius_m)
    exit_diameter_m = 2.0 * float(geometry.exit_radius_m)
    if shell_outer_diameter_m > constraints.max_shell_outer_diameter_m:
        failures.append(
            f"Shell outer diameter {shell_outer_diameter_m:.3f} m exceeds maximum {constraints.max_shell_outer_diameter_m:.3f} m."
        )
    if hot_gas_diameter_m > constraints.max_hot_gas_diameter_m:
        failures.append(
            f"Hot-gas diameter {hot_gas_diameter_m:.3f} m exceeds maximum {constraints.max_hot_gas_diameter_m:.3f} m."
        )
    if geometry.grain_length_m > constraints.max_grain_length_m:
        failures.append(
            f"Grain length {geometry.grain_length_m:.3f} m exceeds maximum {constraints.max_grain_length_m:.3f} m."
        )
    if geometry.chamber_total_length_m > constraints.max_total_chamber_length_m:
        failures.append(
            f"Total chamber length {geometry.chamber_total_length_m:.3f} m exceeds maximum {constraints.max_total_chamber_length_m:.3f} m."
        )
    if geometry.nozzle_total_length_m > constraints.max_nozzle_length_m:
        failures.append(
            f"Nozzle length {geometry.nozzle_total_length_m:.3f} m exceeds maximum {constraints.max_nozzle_length_m:.3f} m."
        )
    if exit_diameter_m > constraints.max_exit_diameter_m:
        failures.append(
            f"Exit diameter {exit_diameter_m:.3f} m exceeds maximum {constraints.max_exit_diameter_m:.3f} m."
        )
    if geometry.area_expansion_ratio > constraints.max_area_expansion_ratio:
        failures.append(
            f"Area ratio {geometry.area_expansion_ratio:.3f} exceeds maximum {constraints.max_area_expansion_ratio:.3f}."
        )
    if geometry.initial_web_thickness_m < constraints.min_initial_web_m:
        failures.append(
            f"Initial web thickness {geometry.initial_web_thickness_m:.4f} m is below minimum {constraints.min_initial_web_m:.4f} m."
        )
    if geometry.final_web_thickness_m < constraints.min_final_web_m:
        failures.append(
            f"Final web thickness {geometry.final_web_thickness_m:.4f} m is below minimum {constraints.min_final_web_m:.4f} m."
        )
    if geometry.grain_slenderness > constraints.max_grain_slenderness:
        failures.append(
            f"Grain slenderness {geometry.grain_slenderness:.3f} exceeds maximum {constraints.max_grain_slenderness:.3f}."
        )
    if geometry.web_slenderness > constraints.max_web_slenderness:
        failures.append(
            f"Web slenderness {geometry.web_slenderness:.3f} exceeds maximum {constraints.max_web_slenderness:.3f}."
        )
    if geometry.lstar_initial_m < constraints.min_lstar_m:
        failures.append(
            f"Characteristic length {geometry.lstar_initial_m:.2f} m is below minimum {constraints.min_lstar_m:.2f} m."
        )
    if geometry.lstar_initial_m > constraints.max_lstar_m:
        failures.append(
            f"Characteristic length {geometry.lstar_initial_m:.2f} m exceeds maximum {constraints.max_lstar_m:.2f} m."
        )
    return failures


def _build_candidate_geometry(
    *,
    hot_gas_radius_candidate_m: float,
    performance: EnginePerformance,
    constraints: EngineConstraints,
    study_config: Mapping[str, Any],
    shell_allowable_stress_pa: float,
    thermal_policy: Mapping[str, Any],
    shell_policy: Mapping[str, Any],
    oxidizer_density_kg_m3: float,
    base_epsilon: float,
    throat_radius_m_value: float,
    nominal_grain_length_m: float,
) -> tuple[EngineGeometry, list[str], dict[str, Any]]:
    geometry_policy = dict(study_config["geometry_policy"])
    thermal = dict(study_config["thermal"])
    nozzle_geometry_cfg = dict(thermal.get("nozzle_geometry", {}))
    liner_thickness_m = _liner_thickness_m(study_config, thermal_policy)
    radial_clearance_m = float(geometry_policy["grain_to_chamber_radial_clearance_m"])
    shell_inner_radius_value_m = float(hot_gas_radius_candidate_m) + liner_thickness_m
    shell_thickness_value_m = selected_shell_thickness_m(
        chamber_pressure_pa=performance.chamber_pressure_pa,
        shell_inner_radius_m=shell_inner_radius_value_m,
        allowable_stress_pa=shell_allowable_stress_pa,
        minimum_wall_thickness_m=float(shell_policy["minimum_wall_thickness_m"]),
        corrosion_allowance_m=float(shell_policy["corrosion_or_manufacturing_allowance_m"]),
        thickness_roundup_increment_m=float(shell_policy["thickness_roundup_increment_m"]),
    )
    shell_outer_radius_value_m = shell_outer_radius_m(shell_inner_radius_value_m, shell_thickness_value_m)
    hot_radius_m = hot_gas_radius_m(shell_inner_radius_value_m, liner_thickness_m)
    grain_outer_radius_value_m = grain_outer_radius_m(hot_radius_m, radial_clearance_m)
    if grain_outer_radius_value_m <= constraints.min_initial_web_m:
        geometry = EngineGeometry(
            shell_inner_radius_m=shell_inner_radius_value_m,
            shell_thickness_m=shell_thickness_value_m,
            liner_thickness_m=liner_thickness_m,
            shell_outer_radius_m=shell_outer_radius_value_m,
            hot_gas_radius_m=hot_radius_m,
            grain_outer_radius_m=max(grain_outer_radius_value_m, 0.0),
            grain_port_radius_initial_m=0.0,
            grain_port_radius_final_m=0.0,
            grain_length_m=0.0,
            radial_clearance_m=radial_clearance_m,
            prechamber_length_m=0.0,
            postchamber_length_m=0.0,
            chamber_total_length_m=0.0,
            throat_radius_m=throat_radius_m_value,
            exit_radius_m=throat_radius_m_value,
            nozzle_converging_length_m=0.0,
            nozzle_diverging_length_m=0.0,
            nozzle_total_length_m=0.0,
            injector_hole_diameter_m=float(study_config["injector_design"]["fixed_hole_diameter_mm"]) * 1.0e-3,
            injector_hole_count=0,
            injector_total_hole_area_m2=0.0,
            initial_web_thickness_m=0.0,
            final_web_thickness_m=0.0,
            grain_slenderness=0.0,
            web_slenderness=0.0,
            lstar_initial_m=0.0,
            area_expansion_ratio=0.0,
            converging_half_angle_deg=float(geometry_policy["alpha_max_deg"]),
            diverging_half_angle_deg=float(geometry_policy["beta_max_deg"]),
            throat_blend_radius_m=0.0,
            hot_gas_free_volume_initial_m3=0.0,
        )
        return geometry, [
            f"Grain outer radius {grain_outer_radius_value_m:.4f} m is not large enough to satisfy the minimum initial web."
        ], {"radius_candidate_m": hot_gas_radius_candidate_m, "status": "grain_outer_radius_too_small"}

    hot_gas_diameter_m = 2.0 * hot_radius_m
    prechamber_length_m_value = _candidate_section_length_m(
        mode=str(geometry_policy["prechamber_length_mode"]),
        hot_gas_diameter_m=hot_gas_diameter_m,
        k_value=float(geometry_policy["k_pre"]),
        minimum_m=float(geometry_policy["L_pre_min_m"]),
        maximum_m=float(geometry_policy["L_pre_max_m"]),
    )
    postchamber_length_m_value = _candidate_section_length_m(
        mode=str(geometry_policy["postchamber_length_mode"]),
        hot_gas_diameter_m=hot_gas_diameter_m,
        k_value=float(geometry_policy["k_post"]),
        minimum_m=float(geometry_policy["L_post_min_m"]),
        maximum_m=float(geometry_policy["L_post_max_m"]),
    )
    r_pi_max_m = max(grain_outer_radius_value_m - constraints.min_initial_web_m, 0.0)
    annulus_area_max_m2 = math.pi * max(grain_outer_radius_value_m**2 - r_pi_max_m**2, 0.0)
    if annulus_area_max_m2 <= 0.0:
        geometry = EngineGeometry(
            shell_inner_radius_m=shell_inner_radius_value_m,
            shell_thickness_m=shell_thickness_value_m,
            liner_thickness_m=liner_thickness_m,
            shell_outer_radius_m=shell_outer_radius_value_m,
            hot_gas_radius_m=hot_radius_m,
            grain_outer_radius_m=grain_outer_radius_value_m,
            grain_port_radius_initial_m=0.0,
            grain_port_radius_final_m=0.0,
            grain_length_m=0.0,
            radial_clearance_m=radial_clearance_m,
            prechamber_length_m=prechamber_length_m_value,
            postchamber_length_m=postchamber_length_m_value,
            chamber_total_length_m=0.0,
            throat_radius_m=throat_radius_m_value,
            exit_radius_m=throat_radius_m_value,
            nozzle_converging_length_m=0.0,
            nozzle_diverging_length_m=0.0,
            nozzle_total_length_m=0.0,
            injector_hole_diameter_m=float(study_config["injector_design"]["fixed_hole_diameter_mm"]) * 1.0e-3,
            injector_hole_count=0,
            injector_total_hole_area_m2=0.0,
            initial_web_thickness_m=0.0,
            final_web_thickness_m=0.0,
            grain_slenderness=0.0,
            web_slenderness=0.0,
            lstar_initial_m=0.0,
            area_expansion_ratio=0.0,
            converging_half_angle_deg=float(geometry_policy["alpha_max_deg"]),
            diverging_half_angle_deg=float(geometry_policy["beta_max_deg"]),
            throat_blend_radius_m=0.0,
            hot_gas_free_volume_initial_m3=0.0,
        )
        return geometry, ["Maximum ignition annulus area collapsed to zero."], {"radius_candidate_m": hot_gas_radius_candidate_m, "status": "zero_annulus_area"}

    grain_length_min_required_m = performance.fuel_mass_required_kg / max(
        performance.fuel_density_kg_m3 * annulus_area_max_m2,
        1.0e-12,
    )
    grain_length_min_loaded_m = performance.loaded_fuel_mass_kg / max(
        performance.fuel_density_kg_m3 * annulus_area_max_m2,
        1.0e-12,
    )
    lstar_offset_m3 = math.pi * hot_radius_m**2 * (prechamber_length_m_value + postchamber_length_m_value)
    lstar_length_min_m = (
        throat_area_m2(throat_radius_m_value) * constraints.min_lstar_m
        - lstar_offset_m3
        + performance.loaded_fuel_mass_kg / max(performance.fuel_density_kg_m3, 1.0e-12)
    ) / max(math.pi * hot_radius_m**2, 1.0e-12)
    grain_length_candidate_m = max(
        grain_length_min_required_m,
        grain_length_min_loaded_m,
        max(lstar_length_min_m, 0.0),
    )
    grain_port_radius_initial_value_m = grain_port_radius_from_fuel_mass(
        fuel_mass_kg=performance.loaded_fuel_mass_kg,
        fuel_density_kg_m3=performance.fuel_density_kg_m3,
        grain_length_m=grain_length_candidate_m,
        grain_outer_radius_m=grain_outer_radius_value_m,
    )
    grain_port_radius_final_value_m = grain_port_radius_from_fuel_mass(
        fuel_mass_kg=performance.remaining_fuel_mass_kg,
        fuel_density_kg_m3=performance.fuel_density_kg_m3,
        grain_length_m=grain_length_candidate_m,
        grain_outer_radius_m=grain_outer_radius_value_m,
    )
    initial_web_value_m = web_thickness_m(grain_outer_radius_value_m, grain_port_radius_initial_value_m)
    final_web_value_m = web_thickness_m(grain_outer_radius_value_m, grain_port_radius_final_value_m)
    chamber_total_length_m_value = prechamber_length_m_value + grain_length_candidate_m + postchamber_length_m_value
    free_volume_initial_m3_value = chamber_free_volume_initial_m3(
        hot_gas_radius_m=hot_radius_m,
        prechamber_length_m=prechamber_length_m_value,
        grain_length_m=grain_length_candidate_m,
        grain_port_radius_initial_m=grain_port_radius_initial_value_m,
        postchamber_length_m=postchamber_length_m_value,
    )
    lstar_value_m = lstar_initial_m(
        free_volume_initial_m3=free_volume_initial_m3_value,
        throat_radius_m=throat_radius_m_value,
    )
    hole_diameter_m = float(study_config["injector_design"]["fixed_hole_diameter_mm"]) * 1.0e-3
    hole_count = injector_hole_count_from_required_area(
        injector_required_total_area_m2(
            ox_mass_flow_kg_s=performance.ox_mass_flow_kg_s,
            discharge_coefficient=float(study_config["nominal"]["blowdown"]["injector"]["cd"]),
            oxidizer_density_kg_m3=oxidizer_density_kg_m3,
            injector_delta_p_pa=performance.injector_delta_p_pa,
        ),
        hole_diameter_m,
    )
    injector_total_area_value_m2 = injector_actual_total_area_m2(hole_count, hole_diameter_m)

    alpha_candidates_deg = [float(geometry_policy["alpha_max_deg"]), float(geometry_policy["alpha_min_deg"])]
    beta_candidates_deg = [float(geometry_policy["beta_max_deg"]), float(geometry_policy["beta_min_deg"])]
    epsilon_upper = min(base_epsilon, constraints.epsilon_max, constraints.max_area_expansion_ratio)
    epsilon_lower = max(constraints.epsilon_min, 1.0)
    if epsilon_upper < epsilon_lower:
        epsilon_upper = epsilon_lower
    epsilon_step = max((epsilon_upper - epsilon_lower) / 10.0, 0.25)
    epsilon_candidates = [epsilon_upper]
    epsilon_value = epsilon_upper - epsilon_step
    while epsilon_value >= epsilon_lower:
        epsilon_candidates.append(epsilon_value)
        epsilon_value -= epsilon_step
    if epsilon_candidates[-1] != epsilon_lower:
        epsilon_candidates.append(epsilon_lower)

    chosen_contour = None
    chosen_epsilon = epsilon_upper
    chosen_alpha = float(geometry_policy["alpha_max_deg"])
    chosen_beta = float(geometry_policy["beta_max_deg"])
    exit_radius_value_m = throat_radius_m_value
    for alpha_deg in alpha_candidates_deg:
        for beta_deg in beta_candidates_deg:
            for epsilon in epsilon_candidates:
                exit_radius_candidate_m = throat_radius_m_value * math.sqrt(max(epsilon, 1.0))
                contour = build_conical_nozzle_contour(
                    chamber_diameter_m=2.0 * hot_radius_m,
                    throat_diameter_m=2.0 * throat_radius_m_value,
                    exit_diameter_m=2.0 * exit_radius_candidate_m,
                    converging_half_angle_deg=alpha_deg,
                    diverging_half_angle_deg=beta_deg,
                    throat_blend_radius_factor=float(nozzle_geometry_cfg["throat_blend_radius_factor"]),
                )
                if contour.nozzle_length_m <= constraints.max_nozzle_length_m and 2.0 * exit_radius_candidate_m <= constraints.max_exit_diameter_m:
                    chosen_contour = contour
                    chosen_epsilon = epsilon
                    chosen_alpha = alpha_deg
                    chosen_beta = beta_deg
                    exit_radius_value_m = exit_radius_candidate_m
                    break
            if chosen_contour is not None:
                break
        if chosen_contour is not None:
            break
    if chosen_contour is None:
        exit_radius_value_m = throat_radius_m_value * math.sqrt(max(epsilon_lower, 1.0))
        chosen_epsilon = epsilon_lower
        chosen_contour = build_conical_nozzle_contour(
            chamber_diameter_m=2.0 * hot_radius_m,
            throat_diameter_m=2.0 * throat_radius_m_value,
            exit_diameter_m=2.0 * exit_radius_value_m,
            converging_half_angle_deg=chosen_alpha,
            diverging_half_angle_deg=chosen_beta,
            throat_blend_radius_factor=float(nozzle_geometry_cfg["throat_blend_radius_factor"]),
        )

    geometry = EngineGeometry(
        shell_inner_radius_m=shell_inner_radius_value_m,
        shell_thickness_m=shell_thickness_value_m,
        liner_thickness_m=liner_thickness_m,
        shell_outer_radius_m=shell_outer_radius_value_m,
        hot_gas_radius_m=hot_radius_m,
        grain_outer_radius_m=grain_outer_radius_value_m,
        grain_port_radius_initial_m=grain_port_radius_initial_value_m,
        grain_port_radius_final_m=grain_port_radius_final_value_m,
        grain_length_m=grain_length_candidate_m,
        radial_clearance_m=radial_clearance_m,
        prechamber_length_m=prechamber_length_m_value,
        postchamber_length_m=postchamber_length_m_value,
        chamber_total_length_m=chamber_total_length_m_value,
        throat_radius_m=throat_radius_m_value,
        exit_radius_m=exit_radius_value_m,
        nozzle_converging_length_m=float(chosen_contour.converging_section_length_m),
        nozzle_diverging_length_m=float(chosen_contour.nozzle_length_m),
        nozzle_total_length_m=float(chosen_contour.converging_section_length_m + chosen_contour.nozzle_length_m),
        injector_hole_diameter_m=hole_diameter_m,
        injector_hole_count=hole_count,
        injector_total_hole_area_m2=injector_total_area_value_m2,
        initial_web_thickness_m=initial_web_value_m,
        final_web_thickness_m=final_web_value_m,
        grain_slenderness=grain_slenderness(grain_length_candidate_m, grain_outer_radius_value_m),
        web_slenderness=web_slenderness(grain_length_candidate_m, initial_web_value_m),
        lstar_initial_m=lstar_value_m,
        area_expansion_ratio=float(chosen_epsilon),
        converging_half_angle_deg=float(chosen_alpha),
        diverging_half_angle_deg=float(chosen_beta),
        throat_blend_radius_m=float(chosen_contour.throat_blend_radius_m),
        hot_gas_free_volume_initial_m3=free_volume_initial_m3_value,
    )
    failures = _build_failure_checks(geometry=geometry, constraints=constraints)
    solver_detail = {
        "radius_candidate_m": hot_gas_radius_candidate_m,
        "grain_length_min_from_required_fuel_mass_m": grain_length_min_required_m,
        "grain_length_min_from_loaded_fuel_mass_m": grain_length_min_loaded_m,
        "grain_length_candidate_m": grain_length_candidate_m,
        "nominal_grain_length_m": nominal_grain_length_m,
        "alpha_deg": chosen_alpha,
        "beta_deg": chosen_beta,
        "epsilon": chosen_epsilon,
        "feasible": not failures,
    }
    return geometry, failures, solver_detail


def build_canonical_engine_state(
    study_config: Mapping[str, Any],
    nominal_payload: Mapping[str, Any],
) -> EngineState:
    """Return the canonical diameter-first engine state built from the nominal 0D result."""

    materials = _materials_from_config(study_config)
    constraints = _constraints_from_config(study_config)
    performance = _performance_from_nominal(study_config, nominal_payload)
    structural_policy = _structural_policy_from_config(study_config["structural"])
    thermal_policy = _thermal_policy_from_config(
        study_config["thermal"],
        float(study_config["nominal"]["performance"]["fuel_temperature_k"]),
    )
    shell_allowable_stress_pa = _allowable_stress_pa(materials.shell_material, structural_policy)
    liner_material = _thermal_material_catalog()[materials.liner_material]
    runtime = nominal_payload["result"]["runtime"]
    derived = runtime["derived"]
    nominal_hot_radius_m = (
        float(derived["grain_outer_radius_mm"]) * 1.0e-3
        + float(study_config["geometry_policy"]["grain_to_chamber_radial_clearance_m"])
    )
    throat_radius_value_m = math.sqrt(float(derived["nozzle_throat_area_mm2"]) * 1.0e-6 / math.pi)
    base_epsilon = float(derived["nozzle_exit_area_mm2"]) / max(float(derived["nozzle_throat_area_mm2"]), 1.0e-12)
    oxidizer_density_kg_m3 = float(derived["design_liquid_density_kg_m3"])
    nominal_grain_length_m = float(derived["grain_length_m"])

    radius_step_m = max(float(study_config["geometry_policy"].get("radius_search_step_m", 0.0005)), 1.0e-4)
    radius_upper_bound_m = min(
        max(0.5 * constraints.max_hot_gas_diameter_m, nominal_hot_radius_m),
        max(0.5 * constraints.max_shell_outer_diameter_m, nominal_hot_radius_m),
    )
    if radius_upper_bound_m < nominal_hot_radius_m:
        radius_upper_bound_m = nominal_hot_radius_m

    radius_candidates_m = [nominal_hot_radius_m]
    next_radius_m = nominal_hot_radius_m + radius_step_m
    while next_radius_m <= radius_upper_bound_m + 1.0e-12:
        radius_candidates_m.append(next_radius_m)
        next_radius_m += radius_step_m
    if radius_candidates_m[-1] < radius_upper_bound_m:
        radius_candidates_m.append(radius_upper_bound_m)

    chosen_geometry: EngineGeometry | None = None
    chosen_failures: list[str] = []
    search_rows: list[dict[str, Any]] = []
    for radius_candidate_m in radius_candidates_m:
        geometry, failures, solver_detail = _build_candidate_geometry(
            hot_gas_radius_candidate_m=radius_candidate_m,
            performance=performance,
            constraints=constraints,
            study_config=study_config,
            shell_allowable_stress_pa=shell_allowable_stress_pa,
            thermal_policy=thermal_policy,
            shell_policy=structural_policy,
            oxidizer_density_kg_m3=oxidizer_density_kg_m3,
            base_epsilon=base_epsilon,
            throat_radius_m_value=throat_radius_value_m,
            nominal_grain_length_m=nominal_grain_length_m,
        )
        search_rows.append(solver_detail)
        chosen_geometry = geometry
        chosen_failures = failures
        if not failures:
            break

    assert chosen_geometry is not None
    geometry_valid = not chosen_failures
    solver_report = {
        "diameter_first_policy_used": True,
        "radius_search_range_m": [radius_candidates_m[0], radius_candidates_m[-1]],
        "radius_search_step_m": radius_step_m,
        "max_diameter_hit": abs(chosen_geometry.hot_gas_radius_m - radius_candidates_m[-1]) <= 1.0e-9,
        "chosen_grain_length_m": chosen_geometry.grain_length_m,
        "chosen_chamber_length_m": chosen_geometry.chamber_total_length_m,
        "chosen_nozzle_length_m": chosen_geometry.nozzle_total_length_m,
        "active_constraints": list(constraints.to_dict().keys()),
        "feasibility_result": geometry_valid,
        "search_trace": search_rows,
    }
    diagnostics = EngineDiagnostics(
        warnings=[] if geometry_valid else ["No feasible geometry satisfied the configured hard bounds."],
        failure_reasons=list(chosen_failures),
        solver_report=solver_report,
    )

    return EngineState(
        materials=materials,
        geometry=chosen_geometry,
        performance=performance,
        constraints=constraints,
        validity=EngineValidity(
            geometry_valid=geometry_valid,
            structural_valid=False,
            thermal_valid=False,
            injector_valid=bool(chosen_geometry.injector_hole_count > 0),
            overall_valid=geometry_valid,
        ),
        diagnostics=diagnostics,
        thermal={
            "liner_material_conductivity_w_mk": liner_material["conductivity_w_mk"],
            "liner_material_density_kg_m3": liner_material["density_kg_m3"],
        },
    )


def update_engine_state_validity(
    state: EngineState,
    *,
    geometry_valid: bool | None = None,
    structural_valid: bool | None = None,
    thermal_valid: bool | None = None,
    injector_valid: bool | None = None,
    failure_reasons: list[str] | None = None,
    warnings: list[str] | None = None,
    solver_report_updates: Mapping[str, Any] | None = None,
    thermal_updates: Mapping[str, Any] | None = None,
    shell_thickness_m: float | None = None,
) -> EngineState:
    """Return an updated canonical state after downstream structural or thermal checks."""

    geometry = state.geometry
    if shell_thickness_m is not None:
        updated_shell_thickness_m = float(shell_thickness_m)
        geometry = replace(
            geometry,
            shell_thickness_m=updated_shell_thickness_m,
            shell_outer_radius_m=shell_outer_radius_m(geometry.shell_inner_radius_m, updated_shell_thickness_m),
        )

    next_geometry_valid = state.validity.geometry_valid if geometry_valid is None else bool(geometry_valid)
    next_structural_valid = state.validity.structural_valid if structural_valid is None else bool(structural_valid)
    next_thermal_valid = state.validity.thermal_valid if thermal_valid is None else bool(thermal_valid)
    next_injector_valid = state.validity.injector_valid if injector_valid is None else bool(injector_valid)

    return EngineState(
        materials=state.materials,
        geometry=geometry,
        performance=state.performance,
        constraints=state.constraints,
        validity=EngineValidity(
            geometry_valid=next_geometry_valid,
            structural_valid=next_structural_valid,
            thermal_valid=next_thermal_valid,
            injector_valid=next_injector_valid,
            overall_valid=all([next_geometry_valid, next_structural_valid, next_thermal_valid, next_injector_valid]),
        ),
        diagnostics=EngineDiagnostics(
            warnings=list(state.diagnostics.warnings if warnings is None else warnings),
            failure_reasons=list(state.diagnostics.failure_reasons if failure_reasons is None else failure_reasons),
            solver_report={**state.diagnostics.solver_report, **dict(solver_report_updates or {})},
        ),
        thermal={**state.thermal, **dict(thermal_updates or {})},
    )
