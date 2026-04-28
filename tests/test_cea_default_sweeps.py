import unittest

from src.cea_hybrid.defaults import get_default_raw_config


class CEADefaultSweepTests(unittest.TestCase):
    def test_default_abs_and_area_ratio_sweeps_use_point_one_step(self):
        raw = get_default_raw_config()

        self.assertEqual(raw["sweeps"]["ae_at"]["step"], 0.1)
        self.assertEqual(raw["sweeps"]["abs_volume_fractions"]["step"], 0.1)
        self.assertEqual(raw["sweeps"]["abs_volume_fractions"]["start"], 0.0)
        self.assertEqual(raw["sweeps"]["abs_volume_fractions"]["stop"], 0.2)


if __name__ == "__main__":
    unittest.main()
