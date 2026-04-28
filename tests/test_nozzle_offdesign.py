from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.config_schema import build_design_config
from src.injector_design import build_injector_synthesis_case
from src.nozzle_offdesign import run_nozzle_offdesign_workflow
from src.simulation.case_runner import run_nominal_case
from src.sizing.geometry_freeze import freeze_first_pass_geometry
from src.structural import run_structural_sizing_workflow
from src.thermal import run_thermal_sizing_workflow
from src.workflows.engine import run_workflow


class NozzleOffDesignSmokeTests(unittest.TestCase):
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
        config["thermal"]["load_source"] = "nominal_0d"
        config["thermal"]["include_corner_case_envelope"] = False
        config["thermal"]["include_internal_ballistics_case"] = False
        config["nozzle_offdesign"]["source_mode"] = "nominal_0d"
        config["nozzle_offdesign"]["include_corner_case_envelope"] = False
        config["nozzle_offdesign"]["include_internal_ballistics_case"] = False
        config["nozzle_offdesign"]["transient_sample_count"] = 6
        config["nozzle_offdesign"]["ambient_cases"] = [
            {
                "case_name": "sea_level_static",
                "altitude_m": 0.0,
                "environment_type": "sea_level_static",
            },
            {
                "case_name": "vacuum",
                "ambient_pressure_pa": 0.0,
                "environment_type": "vacuum",
            },
        ]
        config["nozzle_offdesign"]["ambient_sweep"]["enabled"] = False
        config["nozzle_offdesign"]["ascent_profile"]["enabled"] = False
        return config

    def test_nozzle_offdesign_workflow_exports_expected_files(self):
        config = self._small_config()
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        geometry = freeze_first_pass_geometry(config, None, nominal)
        injector_geometry = build_injector_synthesis_case(config, geometry)["injector_geometry"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            structural_payload = run_structural_sizing_workflow(
                config,
                config["structural"],
                str(Path(tmp_dir) / "structural"),
                geometry=geometry,
                nominal_payload=nominal,
                injector_geometry=injector_geometry,
            )
            thermal_payload = run_thermal_sizing_workflow(
                config,
                config["thermal"],
                str(Path(tmp_dir) / "thermal"),
                geometry=geometry,
                structural_result=structural_payload["result"],
                nominal_payload=nominal,
                injector_geometry=injector_geometry,
            )
            payload = run_nozzle_offdesign_workflow(
                config,
                config["nozzle_offdesign"],
                str(Path(tmp_dir) / "nozzle_offdesign"),
                geometry=geometry,
                nominal_payload=nominal,
                structural_result=structural_payload["result"],
                thermal_result=thermal_payload["result"],
            )

            result = payload["result"]
            output_dir = Path(tmp_dir) / "nozzle_offdesign"
            self.assertEqual(len(payload["environment_cases"]), 2)
            self.assertGreater(len(result.ambient_case_results), 0)
            self.assertIsNotNone(result.sea_level_summary)
            self.assertIsNotNone(result.vacuum_summary)
            self.assertIn(result.separation_result.risk_level, {"low", "moderate", "high", "unknown"})
            self.assertIn(
                result.recommendations.get("recommended_usage_mode"),
                {
                    "acceptable_for_both",
                    "baseline_flight_nozzle",
                    "baseline_ground_test_nozzle",
                    "unsuitable_without_redesign",
                },
            )
            self.assertTrue((output_dir / "nozzle_environment_cases.json").exists())
            self.assertTrue((output_dir / "nozzle_offdesign_results.json").exists())
            self.assertTrue((output_dir / "nozzle_recommendations.json").exists())
            self.assertTrue((output_dir / "nozzle_checks.json").exists())
            self.assertTrue((output_dir / "nozzle_operating_points.csv").exists())
            self.assertTrue((output_dir / "nozzle_transient_offdesign.csv").exists())
            self.assertTrue((output_dir / "nozzle_offdesign_summary.txt").exists())

            exported = json.loads((output_dir / "nozzle_offdesign_results.json").read_text(encoding="utf-8"))
            self.assertIn("governing_case", exported)
            self.assertIn("ambient_case_results", exported)

    def test_nozzle_offdesign_mode_runs_through_shared_workflow(self):
        config = self._small_config()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_workflow(
                mode="nozzle_offdesign",
                output_root=tmp_dir,
                design_override=config,
                structural_override=config["structural"],
                thermal_override=config["thermal"],
                nozzle_offdesign_override=config["nozzle_offdesign"],
            )

            self.assertEqual(result["mode"], "nozzle_offdesign")
            nozzle_dir = result["run"].root / "nozzle_offdesign"
            structural_dir = result["run"].root / "structural"
            thermal_dir = result["run"].root / "thermal"
            self.assertTrue((nozzle_dir / "nozzle_offdesign_summary.txt").exists())
            self.assertTrue((nozzle_dir / "nozzle_offdesign_results.json").exists())
            self.assertTrue((structural_dir / "structural_summary.txt").exists())
            self.assertTrue((thermal_dir / "thermal_summary.txt").exists())
            self.assertIn("result", result["payload"]["payload"])


if __name__ == "__main__":
    unittest.main()
