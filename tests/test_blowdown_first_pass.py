import math
import json
import unittest

import numpy as np

from cea_hybrid.server import _json_safe
from blowdown_hybrid.calculations import build_runtime_inputs
from blowdown_hybrid.config import (
    build_config,
    injector_pressure_drop_fraction_for_mode,
    regression_parameters_for_mode,
)
from blowdown_hybrid.constants import (
    INJECTOR_PRESSURE_DROP_POLICY_NOMINAL,
)
from blowdown_hybrid.defaults import (
    PROJECT_DEFAULT_FUEL_USABLE_FRACTION,
    PROJECT_DEFAULT_INJECTOR_CD,
    PROJECT_DEFAULT_USABLE_OXIDIZER_FRACTION,
)
from blowdown_hybrid.first_pass import (
    blend_density_from_volume_fraction,
    fuel_mass_flow,
    grain_length_from_fuel_mass_flow,
    grain_outer_radius_from_loaded_fuel_mass,
    initial_port_radius_from_target_gox,
    injector_total_area_from_mass_flow,
    liquid_oxidizer_volume,
    oxidizer_mass_flow,
    oxidizer_loaded_mass,
    oxidizer_required_mass,
    tank_volume_from_fill_fraction,
    total_mass_flow_from_thrust,
)
from blowdown_hybrid.thermo import initial_tank_state_from_temperature
from blowdown_hybrid.ui_backend import _points, build_config_from_payload, build_default_ui_config
from blowdown_hybrid.solver import simulate


class FirstPassEquationTests(unittest.TestCase):
    def test_mass_flow_from_thrust_and_isp(self):
        self.assertAlmostEqual(total_mass_flow_from_thrust(4000.0, 250.0), 4000.0 / (9.80665 * 250.0))

    def test_mass_flow_split_from_of_ratio(self):
        mdot_total = 5.0
        of_ratio = 6.0

        self.assertAlmostEqual(oxidizer_mass_flow(mdot_total, of_ratio), (6.0 / 7.0) * mdot_total)
        self.assertAlmostEqual(fuel_mass_flow(mdot_total, of_ratio), mdot_total / 7.0)

    def test_oxidizer_required_mass_from_burn_time(self):
        self.assertAlmostEqual(oxidizer_required_mass(2.5, 8.0), 20.0)

    def test_loaded_oxidizer_mass_from_usable_fraction(self):
        self.assertAlmostEqual(oxidizer_loaded_mass(20.0, 0.8), 25.0)

    def test_liquid_oxidizer_volume_from_mass_and_density(self):
        self.assertAlmostEqual(liquid_oxidizer_volume(20.0, 750.0), 20.0 / 750.0)

    def test_tank_volume_derivation(self):
        volume_m3 = tank_volume_from_fill_fraction(
            liquid_volume_m3=20.0 / 750.0,
            initial_fill_fraction=0.8,
        )

        self.assertAlmostEqual(volume_m3, 20.0 / (750.0 * 0.8))

    def test_fuel_density_blend_calculation(self):
        density = blend_density_from_volume_fraction(
            volume_fraction_component_a=0.2,
            density_a_kg_m3=1050.0,
            density_b_kg_m3=930.0,
        )
        expected = 1.0 / (0.2 / 1050.0 + 0.8 / 930.0)

        self.assertAlmostEqual(density, expected)

    def test_initial_port_radius_derivation(self):
        radius_m = initial_port_radius_from_target_gox(
            mdot_ox_kg_s=2.0,
            port_count=2,
            target_initial_gox_kg_m2_s=250.0,
        )
        expected = math.sqrt(2.0 / (math.pi * 2.0 * 250.0))

        self.assertAlmostEqual(radius_m, expected)

    def test_grain_length_derivation(self):
        grain_length_m = grain_length_from_fuel_mass_flow(
            mdot_f_kg_s=0.6,
            fuel_density_kg_m3=950.0,
            port_count=2,
            initial_port_diameter_m=0.05,
            initial_regression_rate_m_s=0.003,
        )
        expected = 0.6 / (950.0 * 2.0 * math.pi * 0.05 * 0.003)

        self.assertAlmostEqual(grain_length_m, expected)

    def test_outer_radius_derivation(self):
        outer_radius_m = grain_outer_radius_from_loaded_fuel_mass(
            loaded_fuel_mass_kg=4.0,
            fuel_density_kg_m3=950.0,
            port_count=2,
            grain_length_m=0.5,
            initial_port_radius_m=0.015,
        )
        expected = math.sqrt(0.015**2 + (4.0 / 950.0) / (2.0 * math.pi * 0.5))

        self.assertAlmostEqual(outer_radius_m, expected)

    def test_injector_total_area_derivation(self):
        area_m2 = injector_total_area_from_mass_flow(
            mdot_ox_kg_s=2.0,
            injector_cd=0.8,
            oxidizer_liquid_density_kg_m3=750.0,
            injector_delta_p_pa=6.0e5,
        )
        expected = 2.0 / (0.8 * math.sqrt(2.0 * 750.0 * 6.0e5))

        self.assertAlmostEqual(area_m2, expected)


class ManualOverrideRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.seed_case = {
            "target_thrust_n": 4000.0,
            "of": 6.0,
            "isp_s": 260.0,
            "pc_bar": 30.0,
            "oxidizer_temp_k": 293.15,
            "fuel_temp_k": 293.15,
            "abs_vol_frac": 0.1,
            "cstar_mps": 1500.0,
            "cf": 1.45,
            "at_m2": 1.0e-4,
            "ae_m2": 1.2e-3,
        }

    def test_manual_overrides_take_precedence_in_advanced_mode(self):
        runtime = build_runtime_inputs(
            {
                "ui_mode": "advanced",
                "tank": {
                    "volume_m3": 0.04,
                    "initial_mass_kg": 19.0,
                    "initial_temp_k": 290.0,
                    "override_mass_volume": True,
                },
                "injector": {
                    "total_area_m2": 9.0e-5,
                    "override_total_area": True,
                },
                "grain": {
                    "initial_port_radius_m": 0.03,
                    "grain_length_m": 0.6,
                    "outer_radius_m": 0.09,
                    "override_initial_port_radius": True,
                    "override_grain_length": True,
                    "override_outer_radius": True,
                },
            },
            self.seed_case,
        )

        self.assertEqual(runtime["derived"]["tank_mass_volume_source"], "manual_override")
        self.assertEqual(runtime["derived"]["injector_total_area_source"], "manual_override")
        self.assertEqual(runtime["derived"]["initial_port_source"], "manual_override")
        self.assertEqual(runtime["derived"]["grain_length_source"], "manual_override")
        self.assertEqual(runtime["derived"]["outer_radius_source"], "manual_override")
        self.assertAlmostEqual(runtime["derived"]["tank_volume_l"], 40.0)
        self.assertAlmostEqual(runtime["derived"]["tank_initial_mass_kg"], 19.0)
        self.assertAlmostEqual(runtime["derived"]["injector_total_area_mm2"], 90.0)
        self.assertAlmostEqual(runtime["derived"]["initial_port_radius_mm"], 30.0)
        self.assertAlmostEqual(runtime["derived"]["grain_length_m"], 0.6)
        self.assertAlmostEqual(runtime["derived"]["grain_outer_radius_mm"], 90.0)

    def test_basic_mode_derives_tank_state_from_input_temperature(self):
        runtime = build_runtime_inputs(
            {
                "ui_mode": "basic",
                "tank": {
                    "initial_temp_k": 285.0,
                    "volume_m3": 0.04,
                    "initial_mass_kg": 19.0,
                    "override_mass_volume": True,
                },
            },
            self.seed_case,
        )

        tank_state = initial_tank_state_from_temperature(285.0)
        self.assertEqual(runtime["derived"]["tank_mass_volume_source"], "auto_derived")
        self.assertNotAlmostEqual(runtime["derived"]["tank_volume_l"], 40.0)
        self.assertNotAlmostEqual(runtime["derived"]["tank_initial_mass_kg"], 19.0)
        self.assertAlmostEqual(runtime["derived"]["tank_initial_temp_k"], 285.0)
        self.assertAlmostEqual(runtime["derived"]["tank_initial_pressure_bar"], tank_state.p_pa / 1e5)

    def test_regression_preset_mapping_uses_project_default_coefficients(self):
        config = build_config(
            {
                "ui_mode": "basic",
                "grain": {
                    "regression_preset": "project_default_paraffin_abs",
                    "a_reg_si": 9.9e-5,
                    "n_reg": 0.9,
                },
            }
        )

        a_reg_si, n_reg, source = regression_parameters_for_mode(config)

        self.assertAlmostEqual(a_reg_si, 5.0e-5)
        self.assertAlmostEqual(n_reg, 0.5)
        self.assertEqual(source, "preset:project_default_paraffin_abs")

    def test_basic_mode_uses_hidden_project_defaults(self):
        runtime = build_runtime_inputs(
            {
                "ui_mode": "basic",
                "tank": {
                    "initial_temp_k": 285.0,
                    "usable_oxidizer_fraction": 0.5,
                },
                "injector": {
                    "cd": 0.55,
                    "pressure_drop_policy": INJECTOR_PRESSURE_DROP_POLICY_NOMINAL,
                },
                "grain": {
                    "fuel_usable_fraction": 0.5,
                },
            },
            self.seed_case,
        )

        self.assertAlmostEqual(runtime["derived"]["tank_usable_oxidizer_fraction"], PROJECT_DEFAULT_USABLE_OXIDIZER_FRACTION)
        self.assertAlmostEqual(runtime["derived"]["injector_cd"], PROJECT_DEFAULT_INJECTOR_CD)
        self.assertAlmostEqual(runtime["derived"]["fuel_usable_fraction"], PROJECT_DEFAULT_FUEL_USABLE_FRACTION)
        self.assertEqual(runtime["derived"]["tank_usable_fraction_source"], "project_default")
        self.assertEqual(runtime["derived"]["injector_cd_source"], "project_default")
        self.assertEqual(runtime["derived"]["fuel_usable_fraction_source"], "project_default")

    def test_basic_mode_injector_pressure_drop_policy_mapping(self):
        config = build_config(
            {
                "ui_mode": "basic",
                "injector": {
                    "pressure_drop_policy": INJECTOR_PRESSURE_DROP_POLICY_NOMINAL,
                    "delta_p_fraction_of_pc": 0.9,
                },
            }
        )

        fraction, source = injector_pressure_drop_fraction_for_mode(config)

        self.assertAlmostEqual(fraction, 0.2)
        self.assertEqual(source, "policy:nominal")

    def test_manual_feed_loss_model_is_explicit_in_runtime_outputs(self):
        runtime = build_runtime_inputs(
            {
                "ui_mode": "advanced",
                "feed": {
                    "loss_model": "manual_override",
                    "manual_delta_p_pa": 2.5e5,
                },
            },
            self.seed_case,
        )

        self.assertEqual(runtime["derived"]["feed_loss_model"], "manual_override")
        self.assertEqual(runtime["derived"]["feed_loss_source"], "manual_override")
        self.assertAlmostEqual(runtime["derived"]["feed_manual_delta_p_bar"], 2.5)

    def test_invalid_fill_fraction_validation(self):
        with self.assertRaisesRegex(ValueError, "Initial fill fraction"):
            build_config({"tank": {"initial_fill_fraction": 1.0}})

    def test_invalid_usable_fraction_validation(self):
        with self.assertRaisesRegex(ValueError, "Usable oxidizer fraction"):
            build_config({"tank": {"usable_oxidizer_fraction": 0.0}})

    def test_default_burn_time_is_five_seconds(self):
        config = build_config({})
        self.assertAlmostEqual(config["simulation"]["burn_time_s"], 5.0)

    def test_payload_uses_main_oxidizer_temperature_for_tank_temperature(self):
        config = build_config_from_payload(
            {
                "oxidizer_temperature_k": 287.5,
                "ui_mode": "basic",
                "seed_case": "highest_isp",
                "tank": {
                    "volume_l": 28.0,
                    "initial_mass_kg": 18.0,
                    "usable_oxidizer_fraction": 0.95,
                    "initial_fill_fraction": 0.8,
                    "override_mass_volume": False,
                },
                "feed": {
                    "line_id_mm": 12.0,
                    "line_length_m": 1.2,
                    "friction_factor": 0.02,
                    "minor_loss_k_total": 8.0,
                },
                "injector": {
                    "cd": 0.8,
                    "hole_count": 24,
                    "total_area_mm2": 75.0,
                    "override_total_area": False,
                    "pressure_drop_policy": "nominal",
                    "delta_p_mode": "fraction_of_pc",
                    "delta_p_pa": 600000.0,
                    "delta_p_fraction_of_pc": 0.2,
                },
                "grain": {
                    "abs_density_kg_m3": 1050.0,
                    "paraffin_density_kg_m3": 930.0,
                    "regression_preset": "project_default_paraffin_abs",
                    "a_reg_si": 5.0e-5,
                    "n_reg": 0.5,
                    "port_count": 1,
                    "target_initial_gox_kg_m2_s": 250.0,
                    "initial_port_radius_mm": 22.0,
                    "grain_length_m": 0.45,
                    "outer_radius_mm": 45.0,
                    "fuel_usable_fraction": 0.98,
                    "override_initial_port_radius": False,
                    "override_grain_length": False,
                    "override_outer_radius": False,
                },
                "simulation": {
                    "dt_s": 0.02,
                    "burn_time_s": 8.0,
                    "ambient_pressure_bar": 1.01325,
                    "max_inner_iterations": 80,
                    "relaxation": 0.35,
                    "relative_tolerance": 1e-6,
                    "stop_when_tank_quality_exceeds": 0.95,
                },
            }
        )

        self.assertAlmostEqual(config["tank"]["initial_temp_k"], 287.5)


class UiPayloadSafetyTests(unittest.TestCase):
    def test_chart_points_drop_non_finite_values(self):
        points = _points(
            [0.0, 1.0, 2.0, 3.0],
            [4.0, float("inf"), float("nan"), 7.0],
        )

        self.assertEqual(
            points,
            [
                {"x": 0.0, "y": 4.0},
                {"x": 3.0, "y": 7.0},
            ],
        )

    def test_json_safe_replaces_non_finite_numbers_before_serialization(self):
        payload = {
            "progress_ratio": float("nan"),
            "result": {
                "charts": [
                    {"x": 0.0, "y": float("inf")},
                    {"x": 1.0, "y": 2.0},
                ],
            },
        }

        encoded = json.dumps(_json_safe(payload), allow_nan=False)
        decoded = json.loads(encoded)

        self.assertIsNone(decoded["progress_ratio"])
        self.assertIsNone(decoded["result"]["charts"][0]["y"])
        self.assertEqual(decoded["result"]["charts"][1]["y"], 2.0)


class CoupledSolverRegressionTests(unittest.TestCase):
    def test_default_ui_case_stays_physically_consistent_through_late_burn(self):
        seed_case = {
            "target_thrust_n": 4000.0,
            "of": 6.90909090909091,
            "isp_s": 250.48240770627382,
            "pc_bar": 30.0,
            "oxidizer_temp_k": 293.15,
            "fuel_temp_k": 293.15,
            "abs_vol_frac": 0.1,
            "cstar_mps": 1654.299656205319,
            "cf": 1.485712790105902,
            "at_m2": 0.0008974368008491689,
            "ae_m2": 0.004397441221597727,
            "pe_bar": 1.0079881238021096,
            "gamma_e": 1.234280629453023,
            "mw_e": 26.616309522013697,
            "mdot_total_kg_s": 1.6274623478573447,
            "thrust_sl_n": 3997.687613028436,
            "thrust_vac_n": 4443.258344806825,
            "isp_vac_s": 278.4004544629961,
            "cf_vac": 1.65035143815607,
        }
        payload = build_default_ui_config({})
        payload["oxidizer_temperature_k"] = seed_case["oxidizer_temp_k"]
        config = build_config_from_payload(payload)
        runtime = build_runtime_inputs(config, seed_case, include_performance_lookup=True)

        simulation = simulate(
            tank_cfg=runtime["tank"],
            feed_cfg=runtime["feed"],
            injector_cfg=runtime["injector"],
            grain_cfg=runtime["grain"],
            nozzle_cfg=runtime["nozzle"],
            sim_cfg=runtime["simulation"],
            initial_mdot_ox_guess_kg_s=runtime["derived"]["target_mdot_ox_kg_s"],
            initial_pc_guess_pa=runtime["design_point"].chamber_pressure_pa,
        )
        history = simulation["history"]

        self.assertEqual(simulation["stop_reason"], "tank_quality_limit_exceeded")
        self.assertTrue(np.all(history["pc_pa"] <= history["p_inj_in_pa"] + 10.0))
        self.assertTrue(np.all(history["dp_inj_pa"] >= -10.0))
        self.assertGreater(float(np.min(history["mdot_total_kg_s"])), 1.2)
        self.assertLess(float(np.max(history["thrust_actual_n"])), 4500.0)
        self.assertGreater(float(history["thrust_actual_n"][-1]), 3000.0)
        self.assertLess(float(history["thrust_actual_n"][-1]), 3300.0)
        self.assertGreater(float(history["tank_p_pa"][0] / 1e5), 49.0)
        self.assertLess(float(history["tank_p_pa"][0] / 1e5), 52.0)
        self.assertGreater(float(history["tank_p_pa"][-1] / 1e5), 32.0)
        self.assertLess(float(history["tank_p_pa"][-1] / 1e5), 34.0)
        self.assertLess(float(np.max(np.abs(np.diff(history["mdot_total_kg_s"][-20:])))), 0.01)


if __name__ == "__main__":
    unittest.main()
