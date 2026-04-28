from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cfd import run_cfd_workflow
from src.config_schema import build_design_config
from src.injector_design import build_injector_synthesis_case
from src.nozzle_offdesign import run_nozzle_offdesign_workflow
from src.simulation.case_runner import run_nominal_case
from src.sizing.geometry_freeze import freeze_first_pass_geometry
from src.structural import run_structural_sizing_workflow
from src.thermal import run_thermal_sizing_workflow
from src.workflows.engine import run_workflow


class CfdWorkflowSmokeTests(unittest.TestCase):
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
        config["cfd"]["enabled_targets"] = [
            "injector_plenum_plate_flow",
            "headend_prechamber_distribution",
            "nozzle_local_offdesign",
        ]
        config["cfd"]["target_priority_order"] = list(config["cfd"]["enabled_targets"])
        config["cfd"]["include_internal_ballistics_case"] = False
        config["cfd"]["include_corner_case_envelope"] = False
        config["cfd"]["require_internal_ballistics_before_stage2"] = False
        config["cfd"]["generate_correction_templates"] = True
        config["cfd"]["cfd_corrections_source"] = "combined"
        return config

    def test_cfd_workflow_exports_expected_files(self):
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
            nozzle_payload = run_nozzle_offdesign_workflow(
                config,
                config["nozzle_offdesign"],
                str(Path(tmp_dir) / "nozzle_offdesign"),
                geometry=geometry,
                nominal_payload=nominal,
                structural_result=structural_payload["result"],
                thermal_result=thermal_payload["result"],
            )
            payload = run_cfd_workflow(
                config,
                config["cfd"],
                str(Path(tmp_dir) / "cfd"),
                mode="cfd_plan",
                geometry=geometry,
                nominal_payload=nominal,
                injector_geometry=injector_geometry,
                structural_result=structural_payload["result"],
                thermal_result=thermal_payload["result"],
                nozzle_result=nozzle_payload["result"],
            )

            plan = payload["plan"]
            output_dir = Path(tmp_dir) / "cfd"
            self.assertGreater(len(plan.targets), 0)
            self.assertGreater(len(payload["case_definitions"]), 0)
            self.assertTrue((output_dir / "cfd_campaign_plan.json").exists())
            self.assertTrue((output_dir / "cfd_targets.csv").exists())
            self.assertTrue((output_dir / "cfd_case_definitions.json").exists())
            self.assertTrue((output_dir / "cfd_geometry_packages.json").exists())
            self.assertTrue((output_dir / "cfd_boundary_conditions.json").exists())
            self.assertTrue((output_dir / "cfd_operating_points.csv").exists())
            self.assertTrue((output_dir / "cfd_summary.txt").exists())
            self.assertTrue((output_dir / "cfd_corrections.json").exists())
            self.assertTrue((output_dir / "cfd_checks.json").exists())

            exported = json.loads((output_dir / "cfd_campaign_plan.json").read_text(encoding="utf-8"))
            self.assertIn("recommended_next_case_id", exported)
            self.assertIn("targets", exported)

    def test_cfd_apply_corrections_runs_through_shared_workflow(self):
        config = self._small_config()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result_path = Path(tmp_dir) / "cfd_results.json"
            result_path.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "case_id": "01_injector_plenum_plate_flow_nominal_initial",
                                "solver_used": "external_placeholder",
                                "completion_status": "completed",
                                "result_source": "test_fixture",
                                "extracted_key_outputs": {
                                    "injector_cda_multiplier": 0.9,
                                    "nozzle_loss_factor": 0.96,
                                },
                                "notes": ["Synthetic CFD result summary for regression testing."],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config["cfd"]["result_ingest_path"] = str(result_path)

            result = run_workflow(
                mode="cfd_apply_corrections",
                output_root=tmp_dir,
                design_override=config,
                structural_override=config["structural"],
                thermal_override=config["thermal"],
                nozzle_offdesign_override=config["nozzle_offdesign"],
                cfd_override=config["cfd"],
            )

            self.assertEqual(result["mode"], "cfd_apply_corrections")
            cfd_dir = result["run"].root / "cfd"
            self.assertTrue((cfd_dir / "updated_model_overrides.json").exists())
            self.assertTrue((cfd_dir / "cfd_result_summaries.json").exists())
            self.assertTrue((cfd_dir / "cfd_vs_reduced_order_comparison.csv").exists())
            self.assertIn("plan", result["payload"]["payload"])

            updated = json.loads((cfd_dir / "updated_model_overrides.json").read_text(encoding="utf-8"))
            self.assertLess(updated["nominal"]["blowdown"]["injector"]["cd"], config["nominal"]["blowdown"]["injector"]["cd"])
            self.assertLess(
                updated["nominal"]["loss_factors"]["nozzle_discharge_factor"],
                config["nominal"]["loss_factors"]["nozzle_discharge_factor"],
            )


if __name__ == "__main__":
    unittest.main()
