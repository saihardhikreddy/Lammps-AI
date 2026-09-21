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
