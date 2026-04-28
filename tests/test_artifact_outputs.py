from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.artifacts.run_store import create_artifact_run
from src.io_utils import ensure_directory, write_json


class ArtifactOutputSmokeTests(unittest.TestCase):
    def test_manifest_writes_combined_and_index_csv_outputs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            run = create_artifact_run(tmp_dir, "nominal")
            performance_dir = ensure_directory(run.root / "performance")
            (performance_dir / "nominal_metrics.csv").write_text("key,value\nthrust_avg_n,123.4\n", encoding="utf-8")
            (performance_dir / "nominal_summary.txt").write_text("nominal summary\n", encoding="utf-8")
            write_json(performance_dir / "nominal_metrics.json", {"thrust_avg_n": 123.4})
            run.register_section("performance", performance_dir)

            manifest_path = run.write_manifest(status="completed", summary={"status": "completed"})

            self.assertTrue(manifest_path.exists())
            combined_path = run.root / "all_outputs.csv"
            artifact_index_path = run.root / "artifact_index.csv"
            self.assertTrue(combined_path.exists())
            self.assertTrue(artifact_index_path.exists())

            with combined_path.open("r", encoding="utf-8") as handle:
                combined_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["source_file"] == "performance/nominal_metrics.csv" for row in combined_rows))
            self.assertTrue(any(row["source_file"] == "performance/nominal_metrics.json" for row in combined_rows))

            with artifact_index_path.open("r", encoding="utf-8") as handle:
                index_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["relative_path"] == "manifest.json" for row in index_rows))
            self.assertTrue(any(row["relative_path"] == "all_outputs.csv" for row in index_rows))

            latest_run_payload = json.loads((Path(tmp_dir) / "latest_run.json").read_text(encoding="utf-8"))
            self.assertEqual(latest_run_payload["run_id"], run.run_id)


if __name__ == "__main__":
    unittest.main()
