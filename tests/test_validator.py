"""Unit tests for ScriptValidator static AST validator (Script Doctor)."""
import unittest
from app.lammps.validator import ScriptValidator

class TestScriptValidator(unittest.TestCase):
    def setUp(self):
        self.validator = ScriptValidator()

    def test_valid_lj_script(self):
        script = """units lj
atom_style atomic
boundary p p p
lattice fcc 0.84
region box block 0 4 0 4 0 4
create_box 1 box
create_atoms 1 box
pair_style lj/cut 2.5
pair_coeff 1 1 1.0 1.0 2.5
velocity all create 1.0 1234
fix 1 all nvt temp 1.0 1.0 0.5
run 100"""
        res = self.validator.validate_static(script)
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)

    def test_run_without_thermo_frequency_is_warned(self):
        base = "units lj\natom_style atomic\nregion box block 0 4 0 4 0 4\ncreate_box 1 box\n" \
               "create_atoms 1 box\npair_style lj/cut 2.5\npair_coeff 1 1 1.0 1.0 2.5\nfix 1 all nve\n"
        warned = lambda script: any("thermo N" in w for w in self.validator.validate_static(script)["warnings"])  # noqa: E731
        self.assertTrue(warned(base + "run 100"))
        self.assertTrue(warned(base + "thermo_style custom step temp\nrun 100"))  # columns, not frequency
        self.assertTrue(warned(base + "thermo 0\nrun 100"))
        self.assertFalse(warned(base + "thermo 50\nrun 100"))
        self.assertFalse(warned(base + "minimize 1e-4 1e-6 100 1000"))

    def test_repair_puts_thermo_before_the_run(self):
        from app.chatbot.router import ChatbotRouter
        script = "units lj\natom_style atomic\nboundary p p p\nthermo_style custom step temp\nfix 1 all nve\nrun 100"
        fixed, notes = ChatbotRouter._repair_script(None, script, {})
        lines = fixed.splitlines()
        self.assertIn("thermo 50", lines)   # thermo_style alone doesn't set a frequency
        self.assertLess(lines.index("thermo 50"), lines.index("run 100"))  # after the run it does nothing
        fixed, _ = ChatbotRouter._repair_script(None, script.replace("run 100", "thermo 10\nrun 100"), {})
        self.assertNotIn("thermo 50", fixed.splitlines())

    def test_read_data_script_is_valid(self):
        # read_data defines the box and the atoms, so no create_atoms is needed
        script = """units real
atom_style full
boundary p p p
read_data system.data
pair_style lj/cut 10.0
pair_coeff * * 0.1 3.0
fix 1 all nve
timestep 1.0
run 100"""
        res = self.validator.validate_static(script)
        self.assertEqual(res["errors"], [])
        self.assertTrue(res["valid"])

    def test_missing_units(self):
        script = """atom_style atomic
lattice fcc 4.05
create_box 1 box
run 100"""
        res = self.validator.validate_static(script)
        self.assertFalse(res["valid"])
        self.assertTrue(any("units" in e.lower() for e in res["errors"]))

    def test_missing_pair_coeff(self):
        script = """units metal
atom_style atomic
lattice fcc 4.05
region box block 0 4 0 4 0 4
create_box 1 box
create_atoms 1 box
pair_style eam/alloy
fix 1 all nvt temp 300 300 0.1
run 100"""
        res = self.validator.validate_static(script)
        self.assertFalse(res["valid"])
        self.assertTrue(any("pair_coeff" in e.lower() for e in res["errors"]))

    def test_dangerous_timestep_warning(self):
        script = """units metal
atom_style atomic
boundary p p p
lattice fcc 4.05
region box block 0 4 0 4 0 4
create_box 1 box
create_atoms 1 box
pair_style eam/alloy
pair_coeff * * Al_zhou.eam.alloy Al
timestep 0.05
fix 1 all nvt temp 300 300 0.1
run 100"""
        res = self.validator.validate_static(script)
        self.assertTrue(len(res["warnings"]) > 0)
        self.assertTrue(any("timestep" in w.lower() for w in res["warnings"]))
