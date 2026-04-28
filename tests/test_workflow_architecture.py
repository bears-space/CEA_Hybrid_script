from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.config import build_design_config as build_design_config_canonical
from src.config_schema import build_design_config as build_design_config_compat
from src.ui.run_metadata import group_artifacts_by_section
from src.workflows import mode_definitions_payload, resolve_mode_alias
from src.workflows.modes import RUN_ALL_SEQUENCE


class WorkflowArchitectureTests(unittest.TestCase):
    def test_mode_definitions_include_testing_and_cfd_domains(self):
        modes = mode_definitions_payload()
        keys = {item["key"] for item in modes}
        self.assertIn("nominal", keys)
        self.assertIn("cfd_plan", keys)
        self.assertIn("test_readiness", keys)
        self.assertEqual(resolve_mode_alias("coldflow_calibrate"), "hydraulic_calibrate")
        self.assertEqual(resolve_mode_alias("ballistics_1d"), "internal_ballistics")

    def test_run_all_sequence_is_supported_and_excludes_external_ingest_modes(self):
        supported = {item["key"] for item in mode_definitions_payload()}
        self.assertTrue(set(RUN_ALL_SEQUENCE).issubset(supported))
        self.assertNotIn("hydraulic_predict", RUN_ALL_SEQUENCE)
        self.assertNotIn("hydraulic_calibrate", RUN_ALL_SEQUENCE)
        self.assertNotIn("cfd_ingest_results", RUN_ALL_SEQUENCE)
        self.assertNotIn("cfd_apply_corrections", RUN_ALL_SEQUENCE)
        self.assertNotIn("test_ingest_data", RUN_ALL_SEQUENCE)

    def test_config_schema_wrapper_matches_canonical_config_package(self):
        canonical = build_design_config_canonical({})
        compat = build_design_config_compat({})
        self.assertEqual(compat["internal_ballistics"], canonical["internal_ballistics"])
        self.assertEqual(compat["testing"], canonical["testing"])
        self.assertEqual(compat["nozzle_offdesign"], canonical["nozzle_offdesign"])

    def test_ui_artifact_grouping_uses_artifact_index(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            artifact_index_path = root / "artifact_index.csv"
            with artifact_index_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["section", "relative_path", "filename", "extension", "size_bytes"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "section": "performance",
                        "relative_path": "performance/nominal_metrics.csv",
                        "filename": "nominal_metrics.csv",
                        "extension": ".csv",
                        "size_bytes": 12,
                    }
                )
                writer.writerow(
                    {
                        "section": "thermal",
                        "relative_path": "thermal/thermal_summary.txt",
                        "filename": "thermal_summary.txt",
                        "extension": ".txt",
                        "size_bytes": 34,
                    }
                )

            grouped = group_artifacts_by_section(root)
            self.assertEqual(len(grouped["performance"]), 1)
            self.assertEqual(grouped["performance"][0]["relative_path"], "performance/nominal_metrics.csv")
            self.assertEqual(grouped["thermal"][0]["filename"], "thermal_summary.txt")


if __name__ == "__main__":
    unittest.main()
