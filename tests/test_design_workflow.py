from __future__ import annotations

from copy import deepcopy
import unittest

import numpy as np

from src.analysis.corner_cases import run_corner_cases
from src.analysis.sensitivity import run_oat_sensitivity
from src.config_schema import build_design_config
from src.simulation.case_runner import run_nominal_case


class DesignWorkflowSmokeTests(unittest.TestCase):
    def _small_config(self):
        config = build_design_config({})
        config["nominal"]["blowdown"]["simulation"]["dt_s"] = 0.05
        config["nominal"]["blowdown"]["simulation"]["burn_time_s"] = 0.5
        config["constraints"] = {"status": {"allowed": ["completed"]}}
        config["uncertainty"] = {
            "tank_temperature_k": {"mode": "absolute", "value": 1.0},
        }
        config["corner_cases"] = {
            "hot_case": {"tank_temperature_k": "high"},
        }
        return config

    def test_nominal_case_returns_histories_and_metrics(self):
        payload = run_nominal_case(self._small_config())

        self.assertIn(payload["result"]["status"], {"completed", "failed"})
        self.assertIn("t_s", payload["result"]["history"])
        self.assertIn("impulse_total_ns", payload["metrics"])
        self.assertIn("all_pass", payload["constraints"])
        self.assertIn("dp_feed_over_pc", payload["result"]["history"])
        self.assertIn("thrust_transient_actual_n", payload["result"]["history"])
        self.assertIn("geometry_valid", payload["metrics"])

    def test_oat_and_corner_paths_reuse_same_solver(self):
        config = self._small_config()

        oat = run_oat_sensitivity(deepcopy(config))
        corners = run_corner_cases(deepcopy(config))

        self.assertEqual(len(oat["cases"]), len(oat["config"]["uncertainty"]) * 2)
        self.assertEqual(len(corners["corners"]), len(corners["config"]["corner_cases"]))
        self.assertEqual(oat["nominal"]["metrics"]["status"], "completed")
        self.assertEqual(corners["nominal"]["metrics"]["status"], "completed")

    def test_dynamic_performance_changes_over_burn(self):
        payload = run_nominal_case(self._small_config())
        history = payload["result"]["history"]

        self.assertIn("cstar_effective_mps", history)
        self.assertIn("cf_actual", history)
        self.assertGreater(abs(float(history["cstar_effective_mps"][0]) - float(history["cstar_effective_mps"][-1])), 0.0)

    def test_solver_stops_cleanly_when_tank_leaves_supported_two_phase_region(self):
        config = self._small_config()
        config["nominal"]["performance"]["target_thrust_n"] = 6000.0
        config["nominal"]["performance_lookup"] = {"enabled": False}
        config["nominal"]["blowdown"]["simulation"]["dt_s"] = 0.02
        config["nominal"]["blowdown"]["simulation"]["burn_time_s"] = 4.0
        config["nominal"]["blowdown"]["simulation"]["stop_on_quality_limit"] = False
        config["nominal"]["blowdown"]["simulation"]["oxidizer_depletion_policy"] = "burn_time_only"

        payload = run_nominal_case(config)
        history = payload["result"]["history"]

        self.assertEqual(payload["result"]["status"], "completed")
        self.assertIn(payload["result"]["stop_reason"], {"burn_time_reached", "tank_left_two_phase_region"})
        self.assertIn("t_s", history)
        self.assertGreater(len(history["t_s"]), 0)
        self.assertGreater(float(np.min(history["mdot_total_kg_s"])), 0.0)
        self.assertTrue(np.all(history["pc_pa"] <= (history["injector_inlet_pressure_bar"] * 1.0e5) + 10.0))


if __name__ == "__main__":
    unittest.main()
