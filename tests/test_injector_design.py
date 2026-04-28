from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from src.config_schema import build_design_config
from src.injector_design import build_injector_synthesis_case, write_injector_outputs
from src.simulation.case_runner import run_internal_ballistics_case, run_nominal_case
from src.sizing.geometry_freeze import freeze_first_pass_geometry


class InjectorDesignSmokeTests(unittest.TestCase):
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
        config["injector_design"]["allowed_hole_count_values"] = [12, 18, 24, 30, 36]
        config["injector_design"]["maximum_ring_count"] = 5
        return config

    def _frozen_geometry(self, config):
        nominal = run_nominal_case(config, injector_source_override="equivalent_manual")
        return freeze_first_pass_geometry(config, None, nominal)

    def test_injector_synthesis_builds_valid_geometry(self):
        config = self._small_config()
        geometry = self._frozen_geometry(config)

        payload = build_injector_synthesis_case(config, geometry)
        injector_geometry = payload["injector_geometry"]
        effective_model = payload["effective_model"]

        self.assertTrue(injector_geometry.injector_geometry_valid)
        self.assertGreater(injector_geometry.hole_count, 0)
        self.assertGreater(injector_geometry.hole_diameter_m, 0.0)
        self.assertGreater(len(payload["candidates"]), 0)
        self.assertEqual(len(payload["candidates"]), 1)
        self.assertAlmostEqual(
            injector_geometry.hole_diameter_m,
            config["injector_design"]["fixed_hole_diameter_mm"] * 1.0e-3,
            places=12,
        )
        self.assertAlmostEqual(
            effective_model.effective_cda_m2,
            injector_geometry.estimated_effective_cda_m2,
            places=12,
        )
        self.assertLess(abs(injector_geometry.actual_to_required_cda_ratio - 1.0), 0.25)

    def test_injector_export_writes_expected_files(self):
        config = self._small_config()
        geometry = self._frozen_geometry(config)
        payload = build_injector_synthesis_case(config, geometry)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_injector_outputs(
                output_dir,
                engine_geometry=geometry,
                design_point=payload["design_point"],
                requirement=payload["requirement"].to_dict(),
                injector_geometry=payload["injector_geometry"],
                effective_model=payload["effective_model"],
                candidates=payload["candidates"],
            )

            self.assertTrue((output_dir / "injector_geometry.json").exists())
            self.assertTrue((output_dir / "injector_geometry.csv").exists())
            self.assertTrue((output_dir / "injector_rings.csv").exists())
            self.assertTrue((output_dir / "injector_candidates.csv").exists())
            self.assertTrue((output_dir / "injector_summary.txt").exists())
            self.assertTrue((output_dir / "injector_pattern.svg").exists())

            exported = json.loads((output_dir / "injector_geometry.json").read_text(encoding="utf-8"))
            self.assertIn("hole_count", exported)
            self.assertIn("estimated_effective_cda_m2", exported)

    def test_nominal_solver_accepts_geometry_backcalculated_injector(self):
        base_config = self._small_config()
        geometry = self._frozen_geometry(base_config)
        synthesis = build_injector_synthesis_case(base_config, geometry)

        config = deepcopy(base_config)
        config["injector_design"]["solver_injector_source"] = "geometry_backcalculated"
        payload = run_nominal_case(
            config,
            frozen_geometry=geometry,
            injector_geometry=synthesis["injector_geometry"],
        )

        self.assertEqual(payload["metrics"]["status"], "completed")
        self.assertEqual(payload["result"]["runtime"]["derived"]["injector_source"], "geometry_backcalculated")
        self.assertEqual(payload["result"]["runtime"]["injector"].hole_count, synthesis["injector_geometry"].hole_count)

    def test_ballistics_solver_accepts_geometry_backcalculated_injector(self):
        base_config = self._small_config()
        geometry = self._frozen_geometry(base_config)
        synthesis = build_injector_synthesis_case(base_config, geometry)

        config = deepcopy(base_config)
        config["injector_design"]["solver_injector_source"] = "geometry_backcalculated"
        payload = run_internal_ballistics_case(
            config,
            geometry,
            injector_geometry=synthesis["injector_geometry"],
        )

        self.assertEqual(payload["metrics"]["status"], "completed")
        self.assertEqual(payload["result"]["runtime"]["derived"]["injector_source"], "geometry_backcalculated")
        self.assertIn("pc_bar", payload["result"]["history"])


if __name__ == "__main__":
    unittest.main()
