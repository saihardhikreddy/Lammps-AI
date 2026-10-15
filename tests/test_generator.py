"""Unit tests for Liquid-State Intent Extraction, Simulation Planning, and Script Generation."""
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

    def test_extract_molten_aluminum_intent(self):
        spec = self.extractor.extract_intent("Simulate molten aluminum at 1000 K using an NVT ensemble")
        self.assertEqual(spec["intent"], "GENERATE_SCRIPT")
        self.assertEqual(spec["material_name"].lower(), "aluminum")
        self.assertEqual(spec["ensemble"], "NVT")
        self.assertEqual(spec["temperature"], 1000.0)

    def test_extract_molten_nickel_natural_language(self):
        spec = self.extractor.extract_intent("i need a script for molten nickel")
        self.assertEqual(spec["intent"], "GENERATE_SCRIPT")
        self.assertEqual(spec["material_name"].lower(), "nickel")
        self.assertEqual(spec["simulation_type"], "melting")
        res = self.generator.generate(spec)
        self.assertIn("units           metal", res["script"])
        self.assertIn("Ni_u3.eam", res["script"])


    def test_tensile_intent_marked_unsupported(self):
        spec = self.extractor.extract_intent("I want to simulate tensile deformation of copper under strain rate 0.001")
        self.assertEqual(spec["simulation_type"], "unsupported_tensile")
        res = self.generator.generate(spec)
        self.assertIn("out of scope", res["goal"].lower())
        self.assertIn("out of scope", res["script"].lower())
        self.assertIn("solid mechanics", res["limitations"].lower())

    def test_generate_aluminum_script(self):
        spec = self.extractor.extract_intent("Simulate molten aluminum at 1000 K using an NVT ensemble")
        res = self.generator.generate(spec)
        self.assertIn("units           metal", res["script"])
        self.assertIn("pair_style      eam/alloy", res["script"])
        self.assertIn("fix             prod all nvt", res["script"])
        self.assertTrue(len(res["assumptions"]) > 0)
        self.assertTrue(len(res["citations"]) > 0)

    def test_generate_lj_script(self):
        spec = self.extractor.extract_intent("Create a simple Lennard-Jones liquid simulation")
        res = self.generator.generate(spec)
        self.assertIn("units           lj", res["script"])
        self.assertIn("pair_style      lj/cut", res["script"])
        self.assertIn("minimize", res["script"])

    def test_generate_nve_ensemble(self):
        spec = self.extractor.extract_intent("Simulate molten aluminum in the NVE ensemble at 1000 K")
        res = self.generator.generate(spec)
        self.assertIn("fix             prod all nve", res["script"])
        self.assertTrue(any("NVE" in a for a in res["assumptions"]))

    def test_generate_water_spce(self):
        spec = self.extractor.extract_intent("Generate a simulation of water at 300 K in NVT ensemble")
        res = self.generator.generate(spec)
        self.assertIn("units           real", res["script"])
        self.assertIn("atom_style      full", res["script"])
        self.assertIn("fix             rigidH2O all shake 0.0001 20 0 b 1 a 1", res["script"])
        self.assertIn("0.1553 3.166", res["script"])
        self.assertIn("Berendsen", res["citations"][0])

    def test_ensemble_honesty_nvt_nve(self):
        # Requesting NVE must emit 'fix 1 all nve' in production, NOT 'fix 1 all nvt'
        spec_nve = self.extractor.extract_intent("Simulate water in the NVE ensemble at 300 K")
        res_nve = self.generator.generate(spec_nve)
        self.assertIn("fix             prod all nve", res_nve["script"])
        self.assertTrue(any("NVE production" in a for a in res_nve["assumptions"]))

        # Requesting NVT must emit 'fix 1 all nvt' in production
        spec_nvt = self.extractor.extract_intent("Simulate water in the NVT ensemble at 300 K")
        res_nvt = self.generator.generate(spec_nvt)
        self.assertIn("fix             prod all nvt temp 300.0 300.0", res_nvt["script"])

    def test_temperature_phase_sanity_check(self):
        # Water below 273.15 K should trigger freezing warning
        spec_cold_water = self.extractor.extract_intent("Simulate liquid water at 250 K")
        res = self.generator.generate(spec_cold_water)
        self.assertTrue(any("freezing point" in a.lower() for a in res["assumptions"]))

        # Argon below 83.8 K should trigger triple-point warning
        spec_cold_ar = self.extractor.extract_intent("Simulate liquid argon at 60 K")
        res_ar = self.generator.generate(spec_cold_ar)
        self.assertTrue(any("triple point" in a.lower() for a in res_ar["assumptions"]))

    def test_element_symbol_matching(self):
        # Short symbols "ar" and "h2o" must resolve correctly
        spec_ar = self.extractor.extract_intent("Simulate ar at 85 K")
        self.assertEqual(spec_ar["material_name"], "ar")
        self.assertEqual(spec_ar["material_info"]["name"], "Argon")

        spec_water = self.extractor.extract_intent("Simulate h2o at 300 K")
        self.assertEqual(spec_water["material_name"], "h2o")
        self.assertEqual(spec_water["material_info"]["name"], "Water")

    def test_custom_timestep(self):
        spec = self.extractor.extract_intent("Simulate molten aluminum with timestep 0.0005")
        res = self.generator.generate(spec)
        self.assertIn("timestep        0.0005", res["script"])
        self.assertTrue(any("0.0005" in a for a in res["assumptions"]))

if __name__ == "__main__":
    unittest.main()
