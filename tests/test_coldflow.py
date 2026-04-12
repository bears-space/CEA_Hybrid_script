from __future__ import annotations

import csv
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from blowdown_hybrid.hydraulics import feed_pressure_drop_pa

from src.coldflow import build_prediction_context, run_coldflow_calibration_workflow, run_coldflow_prediction_workflow
from src.coldflow.hydraulic_predictor import injector_delta_p_from_mdot
from src.config_schema import build_design_config, normalize_coldflow_config
from src.io_utils import deep_merge
from src.simulation.solver_0d import prepare_runtime_case


class ColdFlowWorkflowTests(unittest.TestCase):
    def _small_config(self):
        config = build_design_config({})
        config["nominal"]["blowdown"]["simulation"]["dt_s"] = 0.05
        config["nominal"]["blowdown"]["simulation"]["burn_time_s"] = 0.5
        config["constraints"] = {"status": {"allowed": ["completed"]}}
        config["uncertainty"] = {"tank_temperature_k": {"mode": "absolute", "value": 1.0}}
        config["corner_cases"] = {}
        return config

    def _coldflow_config(self, config, dataset_path: Path, *, calibration_mode: str = "joint") -> dict:
        override = {
            "dataset_path": str(dataset_path),
            "dataset_name": dataset_path.stem,
            "dataset_format": "csv",
            "calibration_mode": calibration_mode,
            "test_mode": "feed_plus_injector_rig",
            "injector_model_source": "equivalent_manual",
            "fluid": {
                "name": "water",
                "temperature_k": 293.15,
                "density_kg_m3": 997.0,
                "is_surrogate": True,
                "intended_application": "unit-test synthetic rig",
            },
            "rig": {
                "test_mode": "feed_plus_injector_rig",
                "surrogate_fluid_used": True,
            },
        }
        return normalize_coldflow_config(deep_merge(config["coldflow"], override), config)

    def _write_synthetic_dataset(
        self,
        destination: Path,
        config: dict,
        *,
        feed_multiplier: float,
        injector_multiplier: float,
    ) -> None:
        coldflow_config = self._coldflow_config(config, destination)
        context = build_prediction_context(config, coldflow_config)
        actual_feed = replace(
            context.feed_config,
            pressure_drop_multiplier=float(context.feed_config.pressure_drop_multiplier) * float(feed_multiplier),
        )
        actual_injector = replace(
            context.injector_config,
            cd=float(context.injector_config.cd) * float(injector_multiplier),
        )
        density_kg_m3 = float(coldflow_config["fluid"]["density_kg_m3"])
        target_mdot_kg_s = float(context.design_reference["target_mdot_ox_kg_s"])
        measured_mdot_values = [
            0.70 * target_mdot_kg_s,
            0.85 * target_mdot_kg_s,
            1.00 * target_mdot_kg_s,
            1.10 * target_mdot_kg_s,
        ]
        downstream_pressure_pa = 101325.0

        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "test_id",
                    "upstream_pressure_bar",
                    "injector_inlet_pressure_bar",
                    "downstream_pressure_bar",
                    "measured_mdot_kg_s",
                ],
            )
            writer.writeheader()
            for index, measured_mdot_kg_s in enumerate(measured_mdot_values):
                injector_delta_p_pa = injector_delta_p_from_mdot(
                    measured_mdot_kg_s,
                    density_kg_m3,
                    actual_injector,
                )
                feed_delta_p_pa = feed_pressure_drop_pa(
                    measured_mdot_kg_s,
                    density_kg_m3,
                    actual_feed,
                )
                injector_inlet_pressure_pa = downstream_pressure_pa + injector_delta_p_pa
                upstream_pressure_pa = injector_inlet_pressure_pa + feed_delta_p_pa
                writer.writerow(
                    {
                        "test_id": f"pt_{index}",
                        "upstream_pressure_bar": upstream_pressure_pa / 1.0e5,
                        "injector_inlet_pressure_bar": injector_inlet_pressure_pa / 1.0e5,
                        "downstream_pressure_bar": downstream_pressure_pa / 1.0e5,
                        "measured_mdot_kg_s": measured_mdot_kg_s,
                    }
                )

    def test_coldflow_prediction_matches_synthetic_baseline(self):
        config = self._small_config()
        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_path = Path(tmp_dir) / "coldflow_prediction.csv"
            output_dir = Path(tmp_dir) / "output"
            self._write_synthetic_dataset(dataset_path, config, feed_multiplier=1.0, injector_multiplier=1.0)
            coldflow_config = self._coldflow_config(config, dataset_path)

            payload = run_coldflow_prediction_workflow(config, coldflow_config, output_dir)

            self.assertLess(payload["baseline_stats"]["mdot_error_percent"]["rmse"], 1.0e-6)
            self.assertTrue((output_dir / "dataset_cleaned.csv").exists())
            self.assertTrue((output_dir / "coldflow_predictions.csv").exists())
            self.assertTrue((output_dir / "mdot_parity.svg").exists())

    def test_joint_coldflow_calibration_recovers_synthetic_multipliers(self):
        config = self._small_config()
        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_path = Path(tmp_dir) / "coldflow_calibration.csv"
            output_dir = Path(tmp_dir) / "output"
            self._write_synthetic_dataset(dataset_path, config, feed_multiplier=1.35, injector_multiplier=0.92)
            coldflow_config = self._coldflow_config(config, dataset_path, calibration_mode="joint")

            payload = run_coldflow_calibration_workflow(config, coldflow_config, output_dir)
            package = payload["calibration_package"]

            self.assertTrue(package.calibration_valid)
            self.assertAlmostEqual(package.recommended_parameter_updates["feed_loss_multiplier"], 1.35, places=4)
            self.assertAlmostEqual(package.recommended_parameter_updates["injector_cda_multiplier"], 0.92, places=4)
            self.assertLess(payload["calibrated_stats"]["mdot_error_percent"]["rmse"], 1.0e-6)
            self.assertTrue((output_dir / "calibration_package.json").exists())
            self.assertTrue((output_dir / "updated_model_overrides.json").exists())

    def test_prepare_runtime_case_applies_saved_coldflow_package(self):
        base_config = self._small_config()
        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_path = Path(tmp_dir) / "coldflow_runtime.csv"
            output_dir = Path(tmp_dir) / "output"
            self._write_synthetic_dataset(dataset_path, base_config, feed_multiplier=1.20, injector_multiplier=0.88)
            coldflow_config = self._coldflow_config(base_config, dataset_path, calibration_mode="joint")

            payload = run_coldflow_calibration_workflow(base_config, coldflow_config, output_dir)
            package = payload["calibration_package"]

            calibrated_config = self._small_config()
            calibrated_config["coldflow"]["hydraulic_source"] = "coldflow_calibrated"
            calibrated_config["coldflow"]["calibration_package_path"] = str(output_dir / "calibration_package.json")
            calibrated_config["coldflow"]["allow_missing_calibration_package"] = False

            runtime = prepare_runtime_case(calibrated_config)["runtime"]

            self.assertEqual(runtime["derived"]["hydraulic_source"], "coldflow_calibrated")
            self.assertAlmostEqual(
                runtime["feed"].pressure_drop_multiplier,
                package.recommended_parameter_updates["feed_pressure_drop_multiplier_calibrated"],
                places=6,
            )
            self.assertAlmostEqual(
                runtime["injector"].cd,
                base_config["nominal"]["blowdown"]["injector"]["cd"]
                * package.recommended_parameter_updates["injector_cda_multiplier"],
                places=6,
            )


if __name__ == "__main__":
    unittest.main()
