import unittest

from project_data import load_project_defaults


class DefaultNozzleAltitudeTests(unittest.TestCase):
    def test_default_ambient_cases_use_three_and_nine_km_plus_vacuum(self):
        cases = load_project_defaults()["design_workflow"]["nozzle_offdesign"]["ambient_cases"]

        self.assertEqual(cases[0]["case_name"], "sea_level_static")
        self.assertEqual(cases[1]["case_name"], "flight_3km")
        self.assertEqual(cases[1]["altitude_m"], 3000.0)
        self.assertEqual(cases[2]["case_name"], "flight_9km")
        self.assertEqual(cases[2]["altitude_m"], 9000.0)
        self.assertEqual(cases[3]["case_name"], "vacuum")


if __name__ == "__main__":
    unittest.main()
