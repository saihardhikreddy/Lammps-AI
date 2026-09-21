"""Unit tests for Intent Extraction, Simulation Planning, and Script Generation."""
import unittest
from app.generation.intent import IntentExtractor
from app.generation.generator import ScriptGenerator
from app.knowledge.retriever import LocalKnowledgeRetriever

class TestScriptGenerator(unittest.TestCase):
    def setUp(self):
        self.retriever = LocalKnowledgeRetriever()
        self.extractor = IntentExtractor()
        self.generator = ScriptGenerator(self.retriever)

    def test_extract_lj_liquid_intent(self):
        spec = self.extractor.extract_intent("Create a simple Lennard-Jones liquid simulation")
        self.assertEqual(spec["intent"], "GENERATE_SCRIPT")
        self.assertIn("lennard-jones", spec["material_name"].lower())
        self.assertEqual(len(spec["missing_parameters"]), 0)

    def test_extract_aluminum_melting_intent(self):
        spec = self.extractor.extract_intent("Simulate melting of aluminum using an NVT ensemble")
        self.assertEqual(spec["intent"], "GENERATE_SCRIPT")
        self.assertEqual(spec["material_name"].lower(), "aluminum")
        self.assertEqual(spec["simulation_type"], "melting")
        self.assertEqual(spec["ensemble"], "NVT")

    def test_extract_incomplete_tensile_intent(self):
        spec = self.extractor.extract_intent("I want to simulate tensile deformation of a material")
        self.assertEqual(spec["intent"], "GENERATE_SCRIPT")
        self.assertIn("Material / System Composition", spec["missing_parameters"][0])

    def test_generate_aluminum_script(self):
        spec = self.extractor.extract_intent("Simulate melting of aluminum using an NVT ensemble")
        res = self.generator.generate(spec)
        self.assertIn("units           metal", res["script"])
        self.assertIn("pair_style      eam/alloy", res["script"])
        self.assertIn("fix             1 all nvt", res["script"])
        self.assertTrue(len(res["assumptions"]) > 0)
        self.assertTrue(len(res["citations"]) > 0)

    def test_generate_lj_script(self):
        spec = self.extractor.extract_intent("Create a simple Lennard-Jones liquid simulation")
        res = self.generator.generate(spec)
        self.assertIn("units           lj", res["script"])
        self.assertIn("pair_style      lj/cut", res["script"])

    def test_generate_nve_ensemble(self):
        spec = self.extractor.extract_intent("Simulate aluminum in the NVE ensemble at 300 K")
        res = self.generator.generate(spec)
        self.assertIn("fix             1 all nve", res["script"])
        self.assertIn("Ensemble: NVE", res["assumptions"][3])

    def test_generate_aluminum_tensile(self):
        spec = self.extractor.extract_intent("Generate a tensile deformation simulation of aluminum")
        res = self.generator.generate(spec)
        self.assertIn("Aluminum", res["script"])
        self.assertIn("Al_zhou.eam.alloy", res["script"])
        self.assertIn("variable        L0 equal lz", res["script"])
        self.assertIn("variable        strain equal \"(lz - v_L0)/v_L0\"", res["script"])

    def test_custom_timestep(self):
        spec = self.extractor.extract_intent("Simulate melting of aluminum with timestep 0.0005")
        res = self.generator.generate(spec)
        self.assertIn("timestep        0.0005", res["script"])
        self.assertIn("0.0005", res["assumptions"][4])

if __name__ == "__main__":
    unittest.main()

