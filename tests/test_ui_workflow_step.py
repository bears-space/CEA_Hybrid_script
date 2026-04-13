import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ui.server import _workflow_step_payload


class WorkflowStepPayloadTests(unittest.TestCase):
    def test_workflow_step_payload_exposes_raw_csv_tables_and_chart_hints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "thermal").mkdir()
            (root / "thermal" / "thermal_region_histories.csv").write_text(
                "\n".join(
                    [
                        "region,time_s,heat_flux_w_m2,inner_wall_temp_k,outer_wall_temp_k",
                        "throat,0.0,10.0,300.0,295.0",
                        "throat,0.1,11.0,301.0,296.0",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "thermal" / "thermal_sizing.json").write_text(
                '{"warnings": [], "case_summaries": []}',
                encoding="utf-8",
            )

            latest = {
                "run_id": "run-1",
                "requested_mode": "thermal_size",
                "root": str(root),
                "manifest": {"sections": {"thermal": str(root / "thermal")}},
            }

            with patch("src.ui.server._latest_run_payload", return_value=latest):
                payload = _workflow_step_payload("thermal_size")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["step"], "thermal_size")
        self.assertEqual(payload["tables"][0]["relative_path"], "thermal/thermal_region_histories.csv")
        self.assertEqual(payload["tables"][0]["rows"][0]["time_s"], 0)
        self.assertTrue(any(item["table_key"] == "thermal/thermal_region_histories.csv" for item in payload["chart_hints"]))

    def test_config_step_payload_exists_without_latest_run(self):
        with patch("src.ui.server._latest_run_payload", return_value=None):
            payload = _workflow_step_payload("design_config")

        self.assertIsNotNone(payload)
        self.assertIsNotNone(payload["config_snapshot"])
        self.assertEqual(payload["config_snapshot"]["title"], "Design Config")
        self.assertIsNone(payload["run_id"])
        self.assertFalse(payload["downloads"])


if __name__ == "__main__":
    unittest.main()
