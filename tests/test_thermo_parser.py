"""Unit tests for ThermoParser thermodynamic data parsing."""
import unittest
from app.lammps.parser import ThermoParser

class TestThermoParser(unittest.TestCase):
    def setUp(self):
        self.parser = ThermoParser()
        self.sample_log = """
LAMMPS (2 Aug 2023)
Step Temp PotEng TotEng Press Volume
0 300.0 -4.20 -3.80 1.2 2650.0
50 305.2 -4.18 -3.79 0.8 2652.0
100 298.5 -4.22 -3.81 -0.5 2649.0
150 301.1 -4.19 -3.80 1.0 2651.0
200 300.4 -4.20 -3.80 0.2 2650.5
Loop time of 0.2 on 1 procs
"""

    def test_statistical_calculations(self):
        res = self.parser.parse_log_text(self.sample_log)
        self.assertTrue(res["parsed"])
        self.assertIn("Temp", res["summary"])
        temp_stat = res["summary"]["Temp"]
        self.assertAlmostEqual(temp_stat["mean"], 301.04, places=1)
        self.assertIn("time_series", res)
        self.assertEqual(len(res["time_series"]["Temp"]), 5)

    def test_stability_evaluation(self):
        res = self.parser.parse_log_text(self.sample_log)
        self.assertTrue(res["parsed"])
        self.assertIn("stability", res)
        self.assertIn("equilibrated", res["stability"].lower())
