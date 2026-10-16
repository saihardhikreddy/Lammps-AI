"""Unit Tests for Incremental Trajectory Parsing, Async Streaming, and Security Hardening."""
import unittest
import tempfile
import shutil
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.lammps.trajectory_parser import parse_dump_frames
from app.lammps.ovito_renderer import render_final_frame
from app.lammps.runner import SimulationRunner, get_run_state, _run_states


class TestTrajectoryStreaming(unittest.TestCase):
    """Tests trajectory parsing, incomplete frame withholding, and runner security."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.runner = SimulationRunner()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_complete_dump_parsing(self):
        """Verify standard LAMMPS dump file parses all complete frames."""
        dump_file = self.temp_dir / "dump.lammpstrj"
        content = (
            "ITEM: TIMESTEP\n"
            "0\n"
            "ITEM: NUMBER OF ATOMS\n"
            "3\n"
            "ITEM: BOX BOUNDS pp pp pp\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "ITEM: ATOMS id type x y z\n"
            "1 1 1.0 2.0 3.0\n"
            "2 1 4.0 5.0 6.0\n"
            "3 2 7.0 8.0 9.0\n"
            "ITEM: TIMESTEP\n"
            "50\n"
            "ITEM: NUMBER OF ATOMS\n"
            "3\n"
            "ITEM: BOX BOUNDS pp pp pp\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "ITEM: ATOMS id type x y z\n"
            "1 1 1.1 2.1 3.1\n"
            "2 1 4.1 5.1 6.1\n"
            "3 2 7.1 8.1 9.1\n"
        )
        dump_file.write_text(content, encoding="utf-8")

        frames, offset = parse_dump_frames(dump_file, 0)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0]["timestep"], 0)
        self.assertEqual(frames[0]["natoms"], 3)
        self.assertEqual(len(frames[0]["atoms"]), 3)
        self.assertEqual(frames[0]["atoms"][0]["x"], 1.0)
        self.assertEqual(frames[1]["timestep"], 50)
        self.assertEqual(frames[1]["atoms"][2]["type"], 2)
        self.assertGreater(offset, 0)

    def test_incomplete_frame_withheld(self):
        """Verify incomplete / mid-write frames are withheld and offset is preserved."""
        dump_file = self.temp_dir / "dump.lammpstrj"
        # Frame 0 is complete (2 atoms declared and 2 present)
        # Frame 1 is incomplete (2 atoms declared, but file cuts off after 1 atom)
        complete_frame_0 = (
            "ITEM: TIMESTEP\n"
            "0\n"
            "ITEM: NUMBER OF ATOMS\n"
            "2\n"
            "ITEM: BOX BOUNDS pp pp pp\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "ITEM: ATOMS id type x y z\n"
            "1 1 0.0 0.0 0.0\n"
            "2 1 1.0 1.0 1.0\n"
        )
        incomplete_frame_1 = (
            "ITEM: TIMESTEP\n"
            "50\n"
            "ITEM: NUMBER OF ATOMS\n"
            "2\n"
            "ITEM: BOX BOUNDS pp pp pp\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "ITEM: ATOMS id type x y z\n"
            "1 1 0.5 0.5 0.5\n"
            # Missing atom 2!
        )
        dump_file.write_text(complete_frame_0 + incomplete_frame_1, encoding="utf-8")

        frames, offset = parse_dump_frames(dump_file, 0)
        # Only frame 0 should be returned; frame 1 must be withheld
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["timestep"], 0)

        # Now append the missing atom to complete frame 1
        with open(dump_file, "a", encoding="utf-8") as f:
            f.write("2 1 1.5 1.5 1.5\n")

        # Resume reading from the returned offset
        new_frames, final_offset = parse_dump_frames(dump_file, offset)
        self.assertEqual(len(new_frames), 1)
        self.assertEqual(new_frames[0]["timestep"], 50)
        self.assertEqual(len(new_frames[0]["atoms"]), 2)
        self.assertEqual(new_frames[0]["atoms"][1]["x"], 1.5)

    def test_run_id_whitelist_security(self):
        """Verify invalid or malicious run_id values are strictly rejected."""
        dummy_script = self.temp_dir / "in.run"
        dummy_script.write_text("units lj\n", encoding="utf-8")

        malicious_ids = [
            "../../etc/passwd",
            "run/subfolder",
            "run;rm -rf",
            "run id with spaces",
            "run$var",
            "a" * 65,  # exceeds 64 chars
            "",
            "run!special"
        ]

        for bad_id in malicious_ids:
            res = self.runner.run_script(dummy_script, bad_id)
            self.assertFalse(res["success"], f"Should reject malicious run_id: {bad_id}")
            self.assertIn("Security restriction", res["error"])

    def test_forbidden_script_patterns(self):
        """Verify execution blocks scripts containing shell, system, or python escapes."""
        forbidden_scripts = [
            "units metal\nshell rm -rf /\nrun 100\n",
            "units metal\npython exec('import os; os.system(\"calc\")')\nrun 100\n",
            "units metal\nsystem ls -la\nrun 100\n"
        ]

        for i, code in enumerate(forbidden_scripts):
            script_path = self.temp_dir / f"bad_{i}.in"
            script_path.write_text(code, encoding="utf-8")
            res = self.runner.run_script(script_path, f"safe_run_id_{i}")
            self.assertFalse(res["success"])
            self.assertIn("Security restriction", res["error"])

    def test_ovito_renderer_graceful_failure(self):
        """Verify OVITO renderer safely fails without unhandled exception if file missing."""
        missing_dump = self.temp_dir / "nonexistent.lammpstrj"
        output_png = self.temp_dir / "out.png"
        res = render_final_frame(missing_dump, output_png)
        self.assertFalse(res["available"])
        self.assertIn("reason", res)

    def test_async_runner_built_in_execution(self):
        """Verify built-in MD engine executes synchronously when requested and produces valid state."""
        script_code = (
            "units lj\n"
            "atom_style atomic\n"
            "lattice fcc 0.8442\n"
            "create_box 1 box\n"
            "create_atoms 1 box\n"
            "mass 1 1.0\n"
            "velocity all create 1.44 12345\n"
            "pair_style lj/cut 2.5\n"
            "pair_coeff 1 1 1.0 1.0 2.5\n"
            "fix 1 all nvt temp 1.44 1.44 0.5\n"
            "thermo 50\n"
            "dump traj all custom 50 dump.lammpstrj id type x y z\n"
            "run 100\n"
        )
        script_path = self.temp_dir / "in.test"
        script_path.write_text(script_code, encoding="utf-8")

        runner = SimulationRunner(executable_path="builtin")
        res = runner.run_script(
            script_path=script_path,
            run_id="test_built_in_sync",
            sync=True
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "completed")
        self.assertTrue(res["is_synthetic"])
        self.assertEqual(res["engine"], "Local MD Physics Engine (100% Offline)")
        self.assertGreater(len(res["stdout"]), 0)

        # Check state registry
        state = get_run_state("test_built_in_sync")
        self.assertIsNotNone(state)
        self.assertEqual(state["status"], "completed")
        self.assertGreater(len(state["frames"]), 0)
        self.assertIn("kinetic_energy", state.get("available_fields", []))
        # The synthetic engine must not fabricate a stress field
        self.assertNotIn("von_mises_stress", state.get("available_fields", []))
        self.assertTrue(state.get("is_synthetic", False))

        # Check atoms have ke and stress populated
        first_frame = state["frames"][0]
        first_atom = first_frame["atoms"][0]
        self.assertIsNotNone(first_atom[5])
        self.assertEqual(len(first_atom), 6)
        self.assertGreater(first_atom[5], 0.0)

    def test_dump_parsing_with_ke_and_stress(self):
        """Verify dump with c_atomKE and v_vonMises parses into 7-element AtomRecords."""
        dump_file = self.temp_dir / "dump_fields.lammpstrj"
        content = (
            "ITEM: TIMESTEP\n"
            "0\n"
            "ITEM: NUMBER OF ATOMS\n"
            "2\n"
            "ITEM: BOX BOUNDS pp pp pp\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "ITEM: ATOMS id type x y z c_atomKE v_vonMises\n"
            "1 1 1.0 2.0 3.0 0.0452 12.345\n"
            "2 2 4.0 5.0 6.0 0.0789 98.765\n"
        )
        dump_file.write_text(content, encoding="utf-8")

        frames, offset = parse_dump_frames(dump_file, 0)
        self.assertEqual(len(frames), 1)
        atoms = frames[0]["atoms"]
        self.assertEqual(len(atoms), 2)

        # Array indexing: [id, type, x, y, z, ke, stress]
        self.assertEqual(atoms[0][0], 1)
        self.assertEqual(atoms[0][1], 1)
        self.assertAlmostEqual(atoms[0][2], 1.0)
        self.assertAlmostEqual(atoms[0][5], 0.0452)
        self.assertAlmostEqual(atoms[0][6], 12.345)

        # Dict-like backwards compatibility
        self.assertAlmostEqual(atoms[0]["ke"], 0.0452)
        self.assertAlmostEqual(atoms[0]["von_mises_stress"], 12.345)
        self.assertAlmostEqual(atoms[1]["c_atomKE"], 0.0789)
        self.assertAlmostEqual(atoms[1]["v_vonMises"], 98.765)

    def test_dump_parsing_without_ke_and_stress_fallbacks(self):
        """Verify dump without field columns gracefully falls back to None."""
        dump_file = self.temp_dir / "dump_basic.lammpstrj"
        content = (
            "ITEM: TIMESTEP\n"
            "10\n"
            "ITEM: NUMBER OF ATOMS\n"
            "1\n"
            "ITEM: BOX BOUNDS pp pp pp\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "0.0 10.0\n"
            "ITEM: ATOMS id type x y z\n"
            "1 1 2.5 3.5 4.5\n"
        )
        dump_file.write_text(content, encoding="utf-8")

        frames, offset = parse_dump_frames(dump_file, 0)
        self.assertEqual(len(frames), 1)
        atom = frames[0]["atoms"][0]

        self.assertEqual(len(atom), 7)
        self.assertIsNone(atom[5])
        self.assertIsNone(atom[6])
        self.assertIsNone(atom["ke"])
        self.assertIsNone(atom["von_mises_stress"])


if __name__ == "__main__":

    import os
    res = unittest.main(exit=False)
    os._exit(0 if res.result.wasSuccessful() else 1)
