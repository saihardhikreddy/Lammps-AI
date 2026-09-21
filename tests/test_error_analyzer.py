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

if __name__ == "__main__":
    unittest.main()

