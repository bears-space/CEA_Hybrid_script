import json
import tempfile
import unittest
from pathlib import Path

from src.ui.server import _latest_run_dashboard, _section_interactive_charts


class LatestRunDashboardTests(unittest.TestCase):
    def test_dashboard_uses_persisted_output_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "geometry").mkdir()
            (root / "structural").mkdir()
            (root / "thermal").mkdir()
            (root / "nozzle_offdesign").mkdir()
            (root / "performance").mkdir()

            (root / "geometry" / "geometry_definition.json").write_text(
                json.dumps(
                    {
                        "chamber_id_m": 0.1,
                        "chamber_inner_diameter_including_liner_m": 0.1,
                        "chamber_outer_diameter_including_liner_m": 0.11,
                        "chamber_inner_diameter_excluding_liner_m": 0.102,
                        "chamber_outer_diameter_excluding_liner_m": 0.11,
                        "fuel_inner_diameter_m": 0.04,
                        "fuel_outer_diameter_m": 0.09,
                        "throat_diameter_m": 0.03,
                        "nozzle_exit_diameter_m": 0.11,
                        "total_chamber_length_m": 1.45,
                        "inner_liner_thickness_m": 0.001,
                        "injector_hole_count": 43,
                        "injector_total_hole_area_m2": 7.6e-05,
                        "converging_throat_half_angle_deg": 45.0,
                        "diverging_throat_half_angle_deg": 15.0,
                        "throat_blend_radius_m": 0.0225,
                        "converging_section_length_m": 0.14,
                        "converging_section_arc_length_m": 0.15,
                        "converging_straight_length_m": 0.108,
                        "converging_blend_arc_length_m": 0.0177,
                        "nozzle_length_m": 0.28,
                        "nozzle_arc_length_m": 0.3,
                        "nozzle_straight_length_m": 0.274,
                        "nozzle_blend_arc_length_m": 0.0059,
                        "nozzle_contour_style": "conical_blended",
                        "nozzle_profile": {
                            "converging_half_angle_deg": 45.0,
                            "diverging_half_angle_deg": 15.0,
                            "throat_blend_radius_m": 0.0225,
                            "throat_blend_radius_factor": 1.5,
                        },
                        "grain_length_m": 1.1,
                        "prechamber_length_m": 0.18,
                        "postchamber_length_m": 0.17,
                        "geometry_valid": True,
                        "notes": ["Frozen geometry from latest run."],
                    }
                ),
                encoding="utf-8",
            )
            (root / "structural" / "structural_sizing.json").write_text(
                json.dumps({"total_structural_mass_estimate_kg": 4.2}),
                encoding="utf-8",
            )
            (root / "thermal" / "thermal_sizing.json").write_text(
                json.dumps({"throat_region_result": {"peak_inner_wall_temp_k": 2890.5}}),
                encoding="utf-8",
            )
            (root / "nozzle_offdesign" / "nozzle_offdesign_results.json").write_text(
                json.dumps({"sea_level_summary": {"average_thrust_n": 3210.4}}),
                encoding="utf-8",
            )
            (root / "performance" / "nominal_metrics.json").write_text(
                json.dumps({"thrust_avg_n": 3150.2, "pc_avg_bar": 30.1}),
                encoding="utf-8",
            )
            (root / "performance" / "thrust_vs_time.svg").write_text("<svg/>", encoding="utf-8")
            (root / "thermal" / "wall_temperature_vs_time.svg").write_text("<svg/>", encoding="utf-8")

            dashboard = _latest_run_dashboard(
                root,
                {
                    "summary": {
                        "overall_readiness_flag": True,
                        "recommended_next_stage": "material_coupon",
                    }
                },
            )

        labels = {item["label"] for item in dashboard["metrics"]}
        chart_paths = {
            chart["relative_path"]
            for group in dashboard["chart_groups"]
            for chart in group["charts"]
        }

        self.assertIn("Chamber ID Excl. Liner", labels)
        self.assertIn("Chamber OD Excl. Liner", labels)
        self.assertIn("Chamber ID Incl. Liner", labels)
        self.assertIn("Fuel ID", labels)
        self.assertIn("Fuel OD", labels)
        self.assertIn("Average Thrust", labels)
        self.assertIn("Structural Mass", labels)
        self.assertIn("Peak Throat Wall Temp", labels)
        self.assertIn("Nozzle Length", labels)
        self.assertIn("Liner Thickness", labels)
        self.assertIn("Pre Combustion Length", labels)
        self.assertIn("Post Combustion Length", labels)
        self.assertIn("Converging Half-Angle", labels)
        self.assertIn("Injector Hole Count", labels)
        self.assertIn("Injector Total Hole Area", labels)
        self.assertIn("Recommended Next Stage", labels)
        self.assertIn("performance/thrust_vs_time.svg", chart_paths)
        self.assertIn("thermal/wall_temperature_vs_time.svg", chart_paths)
        self.assertTrue(any(group["key"] == "performance" for group in dashboard["chart_groups"]))
        self.assertNotIn("drawing", dashboard)
        self.assertTrue(any(item["label"] == "Overall Readiness" and item["value"] == "Pass" for item in dashboard["metrics"]))

    def test_section_interactive_charts_extract_thermal_histories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "thermal").mkdir()
            (root / "thermal" / "thermal_region_histories.csv").write_text(
                "\n".join(
                    [
                        "region,time_s,heat_flux_w_m2,inner_wall_temp_k,outer_wall_temp_k",
                        "throat,0.0,10.0,300.0,295.0",
                        "throat,0.1,11.0,301.0,296.0",
                        "chamber,0.0,9.0,299.0,294.0",
                        "chamber,0.1,9.5,299.5,294.5",
                    ]
                ),
                encoding="utf-8",
            )

            charts = _section_interactive_charts("thermal", root)

        self.assertEqual(len(charts), 3)
        self.assertEqual(charts[0]["title"], "Heat Flux by Region")
        self.assertEqual(charts[0]["kind"], "line")
        self.assertEqual({series["name"] for series in charts[0]["series"]}, {"throat", "chamber"})


if __name__ == "__main__":
    unittest.main()
