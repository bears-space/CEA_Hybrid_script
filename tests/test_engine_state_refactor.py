from __future__ import annotations

import unittest

from src.config import build_design_config
from src.injector_design import build_injector_synthesis_case
from src.simulation.case_runner import run_nominal_case
from src.sizing.engine_state import EngineState, build_canonical_engine_state
from src.sizing.geometry_freeze import freeze_first_pass_geometry
from src.structural import run_structural_sizing_workflow


class EngineStateRefactorTests(unittest.TestCase):
    def _base_config(self):
        config = build_design_config({})
        config["nominal"]["blowdown"]["simulation"]["dt_s"] = 0.05
        config["nominal"]["blowdown"]["simulation"]["burn_time_s"] = 0.5
        config["constraints"] = {"status": {"allowed": ["completed"]}}
        config["uncertainty"] = {"tank_temperature_k": {"mode": "absolute", "value": 1.0}}
        config["corner_cases"] = {}
        config["geometry_policy"]["require_corner_constraints_pass"] = False
        config["geometry_policy"]["max_shell_outer_diameter_m"] = 0.30
        config["geometry_policy"]["max_hot_gas_diameter_m"] = 0.22
        config["geometry_policy"]["max_grain_length_m"] = 2.0
        config["geometry_policy"]["max_total_chamber_length_m"] = 2.5
        config["geometry_policy"]["max_nozzle_length_m"] = 0.5
        config["geometry_policy"]["max_exit_diameter_m"] = 0.2
        config["geometry_policy"]["max_web_slenderness"] = 120.0
        config["geometry_policy"]["max_grain_slenderness"] = 25.0
        config["geometry_policy"]["min_lstar_m"] = 0.2
        config["geometry_policy"]["max_lstar_m"] = 3.0
        config["geometry_policy"]["epsilon_min"] = 3.0
        config["geometry_policy"]["epsilon_max"] = 24.0
        config["geometry_policy"]["max_area_expansion_ratio"] = 24.0
        config["geometry_policy"]["radius_search_step_m"] = 0.001
        config["structural"]["load_source"] = "nominal_0d"
        config["structural"]["include_corner_case_envelope"] = False
        config["structural"]["include_internal_ballistics_peak_case"] = False
        config["thermal"]["load_source"] = "nominal_0d"
        config["thermal"]["include_corner_case_envelope"] = False
        config["thermal"]["include_internal_ballistics_case"] = False
        return config

    def test_bad_case_fails_for_web_and_length(self):
        config = self._base_config()
        config["geometry_policy"]["min_final_web_m"] = 0.02
        config["geometry_policy"]["max_web_slenderness"] = 8.0
        config["geometry_policy"]["max_total_chamber_length_m"] = 0.20
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")

        state = build_canonical_engine_state(config, nominal)

        self.assertFalse(state.validity.geometry_valid)
        reasons = " ".join(state.diagnostics.failure_reasons)
        self.assertIn("Final web thickness", reasons)
        self.assertIn("Web slenderness", reasons)
        self.assertIn("Total chamber length", reasons)

    def test_diameter_first_policy(self):
        config = self._base_config()
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        baseline = build_canonical_engine_state(config, nominal)
        config["geometry_policy"]["max_grain_length_m"] = baseline.geometry.grain_length_m * 0.99
        config["geometry_policy"]["max_total_chamber_length_m"] = baseline.geometry.chamber_total_length_m * 0.99

        state = build_canonical_engine_state(config, nominal)

        self.assertTrue(state.validity.geometry_valid)
        self.assertGreater(state.geometry.hot_gas_radius_m, baseline.geometry.hot_gas_radius_m)
        self.assertTrue(state.diagnostics.solver_report["diameter_first_policy_used"])

    def test_max_diameter_then_length(self):
        config = self._base_config()
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        baseline = build_canonical_engine_state(config, nominal)
        config["geometry_policy"]["max_grain_length_m"] = baseline.geometry.grain_length_m * 0.98
        config["geometry_policy"]["max_total_chamber_length_m"] = baseline.geometry.chamber_total_length_m * 0.98

        state = build_canonical_engine_state(config, nominal)

        first_feasible = next(row for row in state.diagnostics.solver_report["search_trace"] if row["feasible"])
        self.assertAlmostEqual(state.geometry.grain_length_m, first_feasible["grain_length_candidate_m"])

    def test_total_chamber_length_constraint(self):
        config = self._base_config()
        config["geometry_policy"]["max_total_chamber_length_m"] = 0.10
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")

        state = build_canonical_engine_state(config, nominal)

        self.assertFalse(state.validity.geometry_valid)
        self.assertTrue(any("Total chamber length" in reason for reason in state.diagnostics.failure_reasons))

    def test_nozzle_length_constraint(self):
        config = self._base_config()
        config["geometry_policy"]["max_nozzle_length_m"] = 0.05
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")

        state = build_canonical_engine_state(config, nominal)

        self.assertFalse(state.validity.geometry_valid)
        self.assertTrue(any("Nozzle length" in reason for reason in state.diagnostics.failure_reasons))

    def test_injector_count_consistency(self):
        config = self._base_config()
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        geometry = freeze_first_pass_geometry(config, None, nominal)
        injector_geometry = build_injector_synthesis_case(config, geometry)["injector_geometry"]
        structural_payload = run_structural_sizing_workflow(
            config,
            config["structural"],
            "output/test_structural_consistency",
            geometry=geometry,
            nominal_payload=nominal,
            injector_geometry=injector_geometry,
        )

        structural_state = EngineState.from_mapping(structural_payload["result"].canonical_state)
        self.assertEqual(geometry.injector_hole_count, structural_state.geometry.injector_hole_count)

    def test_material_consistency(self):
        config = self._base_config()
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        geometry = freeze_first_pass_geometry(config, None, nominal)
        structural_payload = run_structural_sizing_workflow(
            config,
            config["structural"],
            "output/test_material_consistency",
            geometry=geometry,
            nominal_payload=nominal,
            injector_geometry=None,
        )

        geometry_state = EngineState.from_mapping(geometry.engine_state)
        structural_state = EngineState.from_mapping(structural_payload["result"].canonical_state)
        self.assertEqual(geometry_state.materials.shell_material, structural_state.materials.shell_material)

    def test_hot_gas_diameter_uses_liner_thickness(self):
        config = self._base_config()
        config["thermal"]["liner"]["enabled"] = True
        config["thermal"]["liner"]["selected_thickness_m"] = 0.002
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")

        state = build_canonical_engine_state(config, nominal)

        shell_inner_diameter_m = 2.0 * state.geometry.shell_inner_radius_m
        hot_gas_diameter_m = 2.0 * state.geometry.hot_gas_radius_m
        self.assertAlmostEqual(hot_gas_diameter_m, shell_inner_diameter_m - 2.0 * state.geometry.liner_thickness_m)

    def test_lstar_constraint(self):
        config = self._base_config()
        config["geometry_policy"]["min_lstar_m"] = 0.2
        config["geometry_policy"]["max_lstar_m"] = 1.5
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")

        state = build_canonical_engine_state(config, nominal)

        self.assertFalse(state.validity.geometry_valid)
        self.assertTrue(any("Characteristic length" in reason for reason in state.diagnostics.failure_reasons))


if __name__ == "__main__":
    unittest.main()
