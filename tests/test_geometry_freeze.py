from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.sensitivity import run_oat_sensitivity
from src.config_schema import build_design_config
from src.post.geometry_export import write_geometry_outputs
from src.simulation.case_runner import run_nominal_case
from src.sizing.geometry_freeze import freeze_first_pass_geometry


class GeometryFreezeSmokeTests(unittest.TestCase):
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
        config["geometry_policy"]["require_corner_constraints_pass"] = False
        return config

    def test_freeze_geometry_returns_structured_definition(self):
        config = self._small_config()
        nominal = run_nominal_case(config)
        oat = run_oat_sensitivity(config)

        geometry = freeze_first_pass_geometry(config, None, nominal, sensitivity_summary=oat)

        self.assertTrue(geometry.geometry_valid)
        self.assertGreater(geometry.chamber_id_m, 0.0)
        self.assertGreater(geometry.throat_diameter_m, 0.0)
        self.assertGreater(geometry.free_volume_initial_m3, 0.0)
        self.assertEqual(geometry.port_count, 1)
        self.assertIn("positive_major_dimensions", geometry.checks)
        self.assertEqual(geometry.sensitivity_driver_metric, config["sensitivity_metrics"][0])
        self.assertEqual(geometry.sensitivity_top_parameter, "tank_temperature_k")

    def test_geometry_export_writes_expected_files(self):
        config = self._small_config()
        nominal = run_nominal_case(config)
        geometry = freeze_first_pass_geometry(config, None, nominal)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_geometry_outputs(output_dir, geometry)

            self.assertTrue((output_dir / "baseline_geometry.json").exists())
            self.assertTrue((output_dir / "baseline_geometry.csv").exists())
            self.assertTrue((output_dir / "geometry_summary.txt").exists())

            payload = json.loads((output_dir / "baseline_geometry.json").read_text(encoding="utf-8"))
            self.assertIn("lstar_initial_m", payload)
            self.assertIn("geometry_valid", payload)


if __name__ == "__main__":
    unittest.main()

