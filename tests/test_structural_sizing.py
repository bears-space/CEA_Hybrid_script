from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.config_schema import build_design_config
from src.injector_design import build_injector_synthesis_case
from src.simulation.case_runner import run_internal_ballistics_case, run_nominal_case
from src.sizing.geometry_freeze import freeze_first_pass_geometry
from src.structural import run_structural_sizing_workflow
from src.workflows.engine import run_workflow


class StructuralSizingSmokeTests(unittest.TestCase):
    def _small_config(self):
        config = build_design_config({})
        config["nominal"]["blowdown"]["simulation"]["dt_s"] = 0.05
        config["nominal"]["blowdown"]["simulation"]["burn_time_s"] = 0.5
        config["constraints"] = {"status": {"allowed": ["completed"]}}
        config["uncertainty"] = {"tank_temperature_k": {"mode": "absolute", "value": 1.0}}
        config["corner_cases"] = {}
        config["geometry_policy"]["min_radial_web_m"] = 0.0
        config["geometry_policy"]["max_port_to_outer_radius_ratio"] = 1.0
        config["geometry_policy"]["max_grain_slenderness_ratio"] = 100.0
        config["geometry_policy"]["max_chamber_to_throat_diameter_ratio"] = 20.0
        config["geometry_policy"]["max_port_to_throat_diameter_ratio"] = 20.0
        config["geometry_policy"]["require_corner_constraints_pass"] = False
        config["internal_ballistics"]["axial_cell_count"] = 7
        config["internal_ballistics"]["time_step_s"] = 0.02
        config["internal_ballistics"]["max_simulation_time_s"] = 0.3
        config["internal_ballistics"]["record_every_n_steps"] = 1
        config["internal_ballistics"]["station_sample_count"] = 3
        config["internal_ballistics"]["compare_to_0d"] = False
        config["structural"]["load_source"] = "nominal_0d"
        config["structural"]["include_corner_case_envelope"] = False
        config["structural"]["include_internal_ballistics_peak_case"] = False
        return config

    def test_structural_sizing_workflow_exports_expected_files(self):
        config = self._small_config()
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        geometry = freeze_first_pass_geometry(config, None, nominal)
        injector_geometry = build_injector_synthesis_case(config, geometry)["injector_geometry"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = run_structural_sizing_workflow(
                config,
                config["structural"],
                tmp_dir,
                geometry=geometry,
                nominal_payload=nominal,
                injector_geometry=injector_geometry,
            )

            result = payload["result"]
            output_dir = Path(tmp_dir)
            self.assertGreater(result.chamber_wall_result.selected_thickness_m, 0.0)
            self.assertGreaterEqual(
                result.chamber_wall_result.selected_thickness_m,
                result.chamber_wall_result.required_thickness_m,
            )
            self.assertIn("chamber_wall_valid", result.validity_flags)
            self.assertTrue((output_dir / "structural_load_cases.json").exists())
            self.assertTrue((output_dir / "structural_sizing.json").exists())
            self.assertTrue((output_dir / "structural_sizing.csv").exists())
            self.assertTrue((output_dir / "structural_summary.txt").exists())
            self.assertTrue((output_dir / "structural_mass_breakdown.csv").exists())
            self.assertTrue((output_dir / "structural_checks.json").exists())

            exported = json.loads((output_dir / "structural_sizing.json").read_text(encoding="utf-8"))
            self.assertIn("governing_load_case", exported)
            self.assertIn("chamber_wall_result", exported)

    def test_structural_mode_runs_through_shared_workflow(self):
        config = self._small_config()
        config["structural"]["load_source"] = "peak_1d"
        config["structural"]["include_internal_ballistics_peak_case"] = True
        config["structural"]["include_nominal_peak_case"] = True

        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        geometry = freeze_first_pass_geometry(config, None, nominal)
        injector_geometry = build_injector_synthesis_case(config, geometry)["injector_geometry"]
        ballistics = run_internal_ballistics_case(config, geometry, injector_geometry=injector_geometry)
        self.assertEqual(ballistics["metrics"]["status"], "completed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_workflow(
                mode="structural_size",
                output_root=tmp_dir,
                design_override=config,
                structural_override=config["structural"],
            )

            self.assertEqual(result["mode"], "structural_size")
            structural_dir = result["run"].root / "structural"
            self.assertTrue((structural_dir / "structural_summary.txt").exists())
            self.assertTrue((structural_dir / "structural_load_cases.json").exists())
            self.assertIn("result", result["payload"]["payload"])


if __name__ == "__main__":
    unittest.main()
