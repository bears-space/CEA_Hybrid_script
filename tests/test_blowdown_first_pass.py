import math
import unittest

from blowdown_hybrid.calculations import build_runtime_inputs
from blowdown_hybrid.first_pass import (
    blend_density_from_volume_fraction,
    fuel_mass_flow,
    grain_length_from_fuel_mass_flow,
    grain_outer_radius_from_loaded_fuel_mass,
    initial_port_radius_from_target_gox,
    injector_total_area_from_mass_flow,
    oxidizer_mass_flow,
    tank_volume_from_fill_fraction,
)


class FirstPassEquationTests(unittest.TestCase):
    def test_mass_flow_split_from_of_ratio(self):
        mdot_total = 5.0
        of_ratio = 6.0

        self.assertAlmostEqual(oxidizer_mass_flow(mdot_total, of_ratio), (6.0 / 7.0) * mdot_total)
        self.assertAlmostEqual(fuel_mass_flow(mdot_total, of_ratio), mdot_total / 7.0)

    def test_tank_volume_derivation(self):
        volume_m3 = tank_volume_from_fill_fraction(
            loaded_oxidizer_mass_kg=20.0,
            oxidizer_liquid_density_kg_m3=750.0,
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

    def test_basic_mode_ignores_manual_override_flags(self):
        runtime = build_runtime_inputs(
            {
                "ui_mode": "basic",
                "tank": {
                    "volume_m3": 0.04,
                    "initial_mass_kg": 19.0,
                    "override_mass_volume": True,
                },
            },
            self.seed_case,
        )

        self.assertEqual(runtime["derived"]["tank_mass_volume_source"], "auto_derived")
        self.assertNotAlmostEqual(runtime["derived"]["tank_volume_l"], 40.0)
        self.assertNotAlmostEqual(runtime["derived"]["tank_initial_mass_kg"], 19.0)


if __name__ == "__main__":
    unittest.main()
