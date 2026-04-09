from __future__ import annotations

from copy import deepcopy
import unittest

from src.analysis.corner_cases import run_corner_cases
from src.analysis.sensitivity import run_oat_sensitivity
from src.config_schema import build_design_config
from src.simulation.case_runner import run_nominal_case


class Step1WorkflowSmokeTests(unittest.TestCase):
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

    def test_oat_and_corner_paths_reuse_same_solver(self):
        config = self._small_config()

        oat = run_oat_sensitivity(deepcopy(config))
        corners = run_corner_cases(deepcopy(config))

        self.assertEqual(len(oat["cases"]), len(oat["config"]["uncertainty"]) * 2)
        self.assertEqual(len(corners["corners"]), len(corners["config"]["corner_cases"]))
        self.assertEqual(oat["nominal"]["metrics"]["status"], "completed")
        self.assertEqual(corners["nominal"]["metrics"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
