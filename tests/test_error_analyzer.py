"""Unit tests for Diagnostic Error Analysis Engine."""
import unittest
from app.lammps.error_analyzer import ErrorAnalyzer
from app.knowledge.retriever import LocalKnowledgeRetriever

class TestErrorAnalyzer(unittest.TestCase):
    def setUp(self):
        retriever = LocalKnowledgeRetriever()
        self.analyzer = ErrorAnalyzer(retriever)

    def test_diagnose_lost_atoms(self):
        err = "ERROR: Lost atoms: original 1000 current 980 (src/thermo.cpp:456)"
        diag = self.analyzer.analyze(err)
        self.assertEqual(diag["identified_command"], "timestep")
        self.assertIn("timestep", diag["suggested_fix"].lower())
        self.assertTrue(len(diag["documentation_citations"]) > 0)

    def test_diagnose_illegal_fix(self):
        err = "ERROR: Illegal fix nvt command (src/modify.cpp:123)"
        diag = self.analyzer.analyze(err)
        self.assertEqual(diag["identified_command"], "fix")
        self.assertIn("fix", diag["suggested_fix"].lower())

    def test_diagnose_illegal_pair_style(self):
        err = "ERROR: Illegal pair_style command (src/force.cpp:321)"
        diag = self.analyzer.analyze(err)
        self.assertEqual(diag["identified_command"], "pair_style")

    def test_diagnose_cannot_open_file(self):
        err = "ERROR: Cannot open potential file Al99.eam.alloy (src/potential.cpp:111)"
        diag = self.analyzer.analyze(err)
        self.assertEqual(diag["identified_command"], "pair_coeff")
        self.assertIn("potential file", diag["suggested_fix"].lower())

    def test_nanoparticle_not_matched_as_nan(self):
        err = "ERROR: Unknown pair style in my gold nanoparticle simulation"
        diag = self.analyzer.analyze(err)
        self.assertNotEqual(diag["identified_command"], "minimize")
        self.assertNotIn("NaN", diag["probable_cause"])

    def test_package_not_in_this_binary(self):
        err = ("ERROR: Unrecognized pair style 'reaxff' is part of the REAXFF package which is not "
               "enabled in this LAMMPS binary. (src/force.cpp:275)")
        diag = self.analyzer.analyze(err)
        self.assertEqual(diag["identified_command"], "package")
        self.assertIn("rebuild", diag["suggested_fix"].lower())

    def test_bond_atoms_missing(self):
        diag = self.analyzer.analyze("ERROR: Bond atoms 12 13 missing on proc 0 at step 200 (src/ntopo_bond_all.cpp:59)")
        self.assertEqual(diag["identified_command"], "comm_modify")
        self.assertIn("timestep", diag["suggested_fix"].lower())

    def test_atoms_outside_the_data_file_box(self):
        diag = self.analyzer.analyze("ERROR: Did not assign all atoms correctly (src/read_data.cpp:1050)")
        self.assertEqual(diag["identified_command"], "read_data")

    def test_fallback_names_the_command_in_longer_messages(self):
        diag = self.analyzer.analyze("ERROR: Illegal compute msd command (src/compute_msd.cpp:41)")
        self.assertEqual(diag["identified_command"], "compute")
        diag = self.analyzer.analyze("ERROR: Unknown command: velocty all create 300 4928 (src/input.cpp:314)")
        self.assertEqual(diag["identified_command"], "velocty")

if __name__ == "__main__":
    unittest.main()

