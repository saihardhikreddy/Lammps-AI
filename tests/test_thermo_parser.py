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

    def test_mid_run_warning_does_not_end_the_table(self):
        log = self.sample_log.replace(
            "100 298.5", "WARNING: Communication cutoff is too small (src/comm.cpp:723)\n100 298.5")
        res = self.parser.parse_log_text(log)
        self.assertEqual(len(res["time_series"]["Temp"]), 5)
        self.assertEqual(len(res["warnings"]), 1)
        self.assertIn("Communication cutoff", res["warnings"][0])

    def test_stability_evaluation(self):
        res = self.parser.parse_log_text(self.sample_log)
        self.assertTrue(res["parsed"])
        self.assertIn("stability", res)
        self.assertIn("equilibrated", res["stability"].lower())

    def test_small_values_keep_their_significant_figures(self):
        # SPC/E water in real units: D ~ 2.3e-05 A^2/fs. Rounding to 4 decimals made it 0.0.
        log = ("Step Temp c_cMSD[4] v_D_fit\n"
               "0 300.0 0.0 0.0\n"
               "1000 299.5 0.142 2.37e-05\n"
               "2000 300.2 0.281 2.34e-05\n"
               "Loop time of 1.0 on 1 procs\n")
        summary = self.parser.parse_log_text(log)["summary"]
        self.assertAlmostEqual(summary["v_D_fit"]["final"], 2.34e-05, delta=1e-9)
        self.assertNotEqual(summary["v_D_fit"]["max"], 0.0)
        # Larger numbers are rounded as before.
        self.assertEqual(summary["Temp"]["mean"], 299.9)
        self.assertEqual(summary["c_cMSD[4]"]["final"], 0.281)
