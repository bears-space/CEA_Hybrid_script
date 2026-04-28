from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.config import build_design_config
from src.injector_design import build_injector_synthesis_case
from src.simulation.case_runner import run_nominal_case
from src.sizing.geometry_freeze import freeze_first_pass_geometry
from src.testing import run_testing_workflow
from src.workflows.engine import run_workflow


class TestingWorkflowSmokeTests(unittest.TestCase):
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
        config["cfd"]["enabled_targets"] = ["injector_plenum_plate_flow"]
        config["cfd"]["target_priority_order"] = list(config["cfd"]["enabled_targets"])
        config["cfd"]["include_internal_ballistics_case"] = False
        config["cfd"]["include_corner_case_envelope"] = False
        config["cfd"]["require_internal_ballistics_before_stage2"] = False
        config["cfd"]["generate_correction_templates"] = False
        config["testing"]["include_cfd_context"] = False
        config["testing"]["require_cfd_before_fullscale"] = False
        config["testing"]["model_vs_test_source"] = "0d"
        config["testing"]["hotfire_corrections_source"] = "staged_combined"
        return config

    def test_testing_workflow_plans_campaign_without_dataset(self):
        config = self._small_config()
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        geometry = freeze_first_pass_geometry(config, None, nominal)
        injector_geometry = build_injector_synthesis_case(config, geometry)["injector_geometry"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = run_testing_workflow(
                config,
                config["testing"],
                str(Path(tmp_dir) / "testing"),
                geometry=geometry,
                nominal_payload=nominal,
                injector_geometry=injector_geometry,
            )

            self.assertTrue((Path(tmp_dir) / "testing" / "test_campaign_plan.json").exists())
            self.assertEqual(payload["campaign_plan"].recommended_next_stage, "material_coupon")
            self.assertEqual(len(payload["articles"]), 5)
            self.assertEqual(len(payload["comparisons"]), 0)

    def test_testing_calibration_runs_through_shared_workflow(self):
        config = self._small_config()
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        history = nominal["result"]["history"]
        dataset = {
            "run_id": "subscale_hotfire_run_001",
            "article_id": "subscale_ballistic_v1",
            "stage_name": "subscale_hotfire",
            "time_series_channels": {
                "time_s": [float(value) for value in history["integration_time_s"][:8]],
                "chamber_pressure_pa": [0.98 * float(value) for value in history["pc_pa"][:8]],
                "tank_pressure_pa": [float(value) for value in history["tank_pressure_pa"][:8]],
                "thrust_n": [1.02 * float(value) for value in history["thrust_n"][:8]],
                "ignition_signal": [0.0, 0.0] + [1.0] * 6,
                "oxidizer_mass_flow_kg_s": [float(value) for value in history["mdot_ox_kg_s"][:8]],
            },
            "metadata": {"stop_reason": "synthetic_fixture"},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_path = Path(tmp_dir) / "hotfire_dataset.json"
            dataset_path.write_text(json.dumps({"datasets": [dataset]}), encoding="utf-8")
            config["testing"]["dataset_path"] = str(dataset_path)

            result = run_workflow(
                mode="test_calibrate_hotfire",
                output_root=tmp_dir,
                design_override=config,
                structural_override=config["structural"],
                thermal_override=config["thermal"],
                nozzle_offdesign_override=config["nozzle_offdesign"],
                cfd_override=config["cfd"],
                testing_override=config["testing"],
            )

            self.assertEqual(result["mode"], "test_calibrate_hotfire")
            testing_dir = result["run"].root / "testing"
            self.assertTrue((testing_dir / "test_campaign_plan.json").exists())
            self.assertTrue((testing_dir / "test_run_summaries.csv").exists())
            self.assertTrue((testing_dir / "model_vs_test_comparisons.csv").exists())
            self.assertTrue((testing_dir / "hotfire_calibration_packages.json").exists())
            self.assertTrue((testing_dir / "updated_model_overrides_from_tests.json").exists())
            payload = result["payload"]["payload"]
            self.assertGreater(len(payload["comparisons"]), 0)
            self.assertGreater(len(payload["calibration_packages"]), 0)

            updated = json.loads((testing_dir / "updated_model_overrides_from_tests.json").read_text(encoding="utf-8"))
            self.assertNotEqual(
                updated["nominal"]["loss_factors"]["cstar_efficiency"],
                config["nominal"]["loss_factors"]["cstar_efficiency"],
            )


if __name__ == "__main__":
    unittest.main()
