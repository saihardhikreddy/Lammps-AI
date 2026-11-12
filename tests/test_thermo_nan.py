"""A run that blows up prints nan/inf in its thermo table."""
import json
import math
import unittest

from app.lammps.parser import ThermoParser

HEADER = "Step Temp PotEng Press\n"


def log(rows, end="Loop time of 1.0 on 1 procs\n"):
    return HEADER + "".join(rows) + end


class BlownUpRunTests(unittest.TestCase):
    def test_short_blown_up_run_is_not_equilibrated(self):
        r = ThermoParser().parse_log_text(log(["0 300 -100 1.0\n", "100 310 -99 2.0\n",
                                               "200 nan nan nan\n", "300 -nan -nan -inf\n"]))
        self.assertTrue(r["stability"].startswith("Unstable (2 thermo row(s)"))
        self.assertEqual(r["stability_analysis"]["non_finite_rows"], 2)
        temp = r["summary"]["Temp"]
        self.assertEqual((temp["mean"], temp["final"], temp["non_finite"]), (305.0, 310.0, 2))
        self.assertEqual(r["time_series"]["Temp"], [300.0, 310.0, None, None])

    def test_result_is_valid_json(self):
        rows = [f"{i * 100} {300 + i} -100 1.0\n" for i in range(10)] + ["1000 nan nan nan\n"] * 4
        r = ThermoParser().parse_log_text(log(rows))
        text = json.dumps(r, allow_nan=False)  # raises if any NaN/inf is left
        self.assertIn("Unstable", json.loads(text)["stability"])

    def test_column_that_is_all_nan(self):
        r = ThermoParser().parse_log_text(log(["0 300 nan 1\n", "1 301 nan 1\n"]))
        self.assertEqual(r["summary"]["PotEng"], {"non_finite": 2})
        json.dumps(r, allow_nan=False)

    def test_clean_run_is_unchanged(self):
        rows = [f"{i * 100} {300 + (i % 2)} -100 1.0\n" for i in range(20)]
        r = ThermoParser().parse_log_text(log(rows))
        self.assertEqual(r["stability"], "Equilibrated")
        self.assertNotIn("non_finite", r["summary"]["Temp"])
        self.assertTrue(all(math.isfinite(v) for v in r["time_series"]["Temp"]))


if __name__ == "__main__":
    unittest.main()
