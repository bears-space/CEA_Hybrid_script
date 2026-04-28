from __future__ import annotations

import unittest

from src.config import build_design_config
from src.simulation.case_runner import run_internal_ballistics_case, run_nominal_case
from src.sizing.geometry_freeze import freeze_first_pass_geometry


class InternalBallisticsSmokeTests(unittest.TestCase):
    def _small_config(self):
        config = build_design_config({})
        config["nominal"]["blowdown"]["simulation"]["dt_s"] = 0.05
        config["nominal"]["blowdown"]["simulation"]["burn_time_s"] = 0.5
        config["constraints"] = {"status": {"allowed": ["completed"]}}
        config["uncertainty"] = {
            "tank_temperature_k": {"mode": "absolute", "value": 1.0},
        }
        config["corner_cases"] = {}
        config["geometry_policy"]["min_radial_web_m"] = 0.0
        config["geometry_policy"]["max_port_to_outer_radius_ratio"] = 1.0
        config["geometry_policy"]["max_grain_slenderness_ratio"] = 100.0
        config["geometry_policy"]["max_chamber_to_throat_diameter_ratio"] = 20.0
        config["geometry_policy"]["max_port_to_throat_diameter_ratio"] = 20.0
        config["geometry_policy"]["require_corner_constraints_pass"] = False
        config["internal_ballistics"]["axial_cell_count"] = 7
        config["internal_ballistics"]["time_step_s"] = 0.02
        config["internal_ballistics"]["max_simulation_time_s"] = 0.4
        config["internal_ballistics"]["record_every_n_steps"] = 1
        config["internal_ballistics"]["station_sample_count"] = 3
        config["internal_ballistics"]["compare_to_0d"] = False
        config["internal_ballistics"]["max_port_growth_fraction_per_step"] = 0.5
        return config

    def test_internal_ballistics_runs_from_frozen_geometry(self):
        config = self._small_config()
        nominal = run_nominal_case(config)
        geometry = freeze_first_pass_geometry(config, None, nominal)

        payload = run_internal_ballistics_case(config, geometry)

        self.assertEqual(payload["metrics"]["status"], "completed")
        self.assertIn("pc_bar", payload["result"]["history"])
        self.assertIn("port_radius_m", payload["result"]["axial_history"])
        self.assertIn("wetted_perimeter_m", payload["result"]["axial_history"])
        self.assertIn("oxidizer_mass_flow_kg_s", payload["result"]["axial_history"])
        self.assertIsNotNone(payload["result"]["final_state"])
        self.assertEqual(
            payload["result"]["axial_history"]["port_radius_m"].shape[1],
            config["internal_ballistics"]["axial_cell_count"],
        )
        self.assertIn("port_diameter_mid_final_mm", payload["metrics"])
        self.assertIn("oxidizer_flux_max_kg_m2_s", payload["metrics"])

    def test_internal_ballistics_can_compare_against_nominal_0d(self):
        config = self._small_config()
        nominal = run_nominal_case(config)
        geometry = freeze_first_pass_geometry(config, None, nominal)

        payload = run_internal_ballistics_case(config, geometry, compare_payload=nominal)

        self.assertIsNotNone(payload["comparison"])
        self.assertIn("rows", payload["comparison"])
        self.assertTrue(any(row["metric"] == "impulse_total_ns" for row in payload["comparison"]["rows"]))

    def test_internal_ballistics_terminal_snapshot_matches_end_of_run_geometry(self):
        config = self._small_config()
        config["nominal"]["blowdown"]["grain"]["a_reg_si"] = 1.0e-5
        config["nominal"]["blowdown"]["simulation"]["dt_s"] = 0.01
        config["nominal"]["blowdown"]["simulation"]["burn_time_s"] = 0.01
        config["internal_ballistics"]["time_step_s"] = 0.01
        config["internal_ballistics"]["max_simulation_time_s"] = 0.01
        config["internal_ballistics"]["max_port_growth_fraction_per_step"] = 10.0

        nominal = run_nominal_case(config)
        geometry = freeze_first_pass_geometry(config, None, nominal)
        payload = run_internal_ballistics_case(config, geometry)

        self.assertEqual(payload["metrics"]["stop_reason"], "burn_time_reached")
        final_state = payload["result"]["final_state"]
        axial_history = payload["result"]["axial_history"]
        history = payload["result"]["history"]
        mid_index = len(axial_history["x_m"]) // 2

        self.assertAlmostEqual(final_state.time_s, history["integration_time_s"][-1])
        self.assertAlmostEqual(axial_history["time_s"][-1], final_state.time_s)
        self.assertAlmostEqual(
            axial_history["port_radius_mm"][-1, mid_index],
            payload["metrics"]["port_radius_final_mm"],
        )


if __name__ == "__main__":
    unittest.main()
