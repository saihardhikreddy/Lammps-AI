"""Unit tests for unit-aware and RDF-derived coordination analysis in ovito_renderer."""
import unittest
import tempfile
import shutil
from pathlib import Path
import numpy as np

from app.lammps.ovito_renderer import (
    detect_units,
    find_first_rdf_minimum,
    render_final_frame,
    UNIT_DEFAULT_CUTOFFS,
    DEFAULT_CUTOFF
)


class TestOvitoUnitAwareCutoff(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_detect_units_explicit(self):
        """Explicit units argument takes precedence."""
        dump_path = self.test_dir / "dump.lammpstrj"
        self.assertEqual(detect_units(dump_path, "lj"), "lj")
        self.assertEqual(detect_units(dump_path, "REAL"), "real")
        self.assertEqual(detect_units(dump_path, " Metal "), "metal")

    def test_detect_units_from_in_script(self):
        """Units detected from in.run or other .in files in parent directory."""
        dump_path = self.test_dir / "dump.lammpstrj"
        dump_path.write_text("ITEM: TIMESTEP\n0\n", encoding="utf-8")
        
        in_file = self.test_dir / "in.run"
        in_file.write_text("# Test script\nunits real\natom_style full\n", encoding="utf-8")
        
        self.assertEqual(detect_units(dump_path), "real")

    def test_detect_units_from_log_lammps(self):
        """Units detected from log.lammps if input script is missing."""
        dump_path = self.test_dir / "dump.lammpstrj"
        dump_path.write_text("ITEM: TIMESTEP\n0\n", encoding="utf-8")

        log_file = self.test_dir / "log.lammps"
        log_file.write_text(
            "LAMMPS (2 Aug 2023)\n"
            "Setting up Verlet run ...\n"
            "  Unit style       : lj\n"
            "  Current step     : 0\n",
            encoding="utf-8"
        )

        self.assertEqual(detect_units(dump_path), "lj")

    def test_detect_units_fallback(self):
        """Fallback to metal when no hints exist."""
        dump_path = self.test_dir / "dump.lammpstrj"
        self.assertEqual(detect_units(dump_path), "metal")

    def test_find_first_rdf_minimum_lj(self):
        """Verify dynamic first minimum detection for LJ units."""
        # Synthesize typical LJ liquid g(r):
        # r: 0.0 to 2.5
        r = np.linspace(0.1, 2.5, 100)
        # Peak at r ~ 1.08, minimum at r ~ 1.50, second peak at r ~ 2.1
        gr = np.exp(-((r - 1.08) ** 2) / 0.02) * 3.5 + np.exp(-((r - 2.10) ** 2) / 0.08) * 1.4 + 0.3
        # Repulsive core: 0 below 0.95
        gr[r < 0.95] = 0.0

        r_min = find_first_rdf_minimum(r, gr, "lj")
        self.assertIsNotNone(r_min)
        self.assertGreaterEqual(r_min, 1.40)
        self.assertLessEqual(r_min, 1.65)

    def test_find_first_rdf_minimum_real(self):
        """Verify dynamic first minimum detection for real/water units."""
        # Synthesize typical water g_OO(r):
        # Peak at ~2.8 A, first minimum at ~3.35 A
        r = np.linspace(1.5, 5.0, 100)
        gr = np.exp(-((r - 2.80) ** 2) / 0.04) * 3.0 + np.exp(-((r - 4.50) ** 2) / 0.15) * 1.2 + 0.5
        gr[r < 2.4] = 0.0

        r_min = find_first_rdf_minimum(r, gr, "real")
        self.assertIsNotNone(r_min)
        self.assertGreaterEqual(r_min, 3.20)
        self.assertLessEqual(r_min, 3.60)

    def test_find_first_rdf_minimum_invalid_data(self):
        """Verify graceful fallback (None) when data is insufficient or monotonic."""
        # Too short
        self.assertIsNone(find_first_rdf_minimum([1.0, 2.0], [1.0, 1.0], "lj"))
        # Flat (gas)
        r = np.linspace(0.5, 3.0, 50)
        gr = np.ones_like(r) * 0.5
        self.assertIsNone(find_first_rdf_minimum(r, gr, "lj"))

    def test_unit_default_cutoffs(self):
        """Verify dictionary contains expected defaults for all standard units."""
        self.assertEqual(UNIT_DEFAULT_CUTOFFS["lj"], 1.5)
        self.assertEqual(UNIT_DEFAULT_CUTOFFS["real"], 3.35)
        self.assertEqual(UNIT_DEFAULT_CUTOFFS["metal"], 3.4)
        self.assertEqual(DEFAULT_CUTOFF, 3.5)

    def test_render_missing_dump(self):
        """Missing dump gracefully returns available=False."""
        missing = self.test_dir / "does_not_exist.lammpstrj"
        out_png = self.test_dir / "out.png"
        res = render_final_frame(missing, out_png)
        self.assertFalse(res["available"])
        self.assertIn("reason", res)


if __name__ == "__main__":
    unittest.main()
