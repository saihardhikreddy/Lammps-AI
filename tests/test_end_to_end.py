"""Comprehensive End-to-End Suite Testing 10+ Realistic Research Scenarios."""
import unittest
import uuid
from app.chatbot.router import ChatbotRouter
from app.lammps.detector import detect_lammps

class TestLAMMPSEndToEndScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = ChatbotRouter()
        cls.router.gemini_client.is_available = lambda: False
        cls.router.local_llm.is_available = lambda: False

    # Scenario 1: Explain Lennard-Jones potential
    def test_scenario_01_explain_lj(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "Explain pair_style lj/cut and its potential formula")
        self.assertIn("pair_style", res["answer"].lower())
        self.assertTrue(len(res["citations"]) > 0)
        self.assertTrue(any("pair_style" in c.lower() for c in res["citations"]))

    # Scenario 2: How does fix nvt work?
    def test_scenario_02_fix_nvt(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "How does fix nvt work?")
        self.assertIn("nvt", res["answer"].lower())
        self.assertTrue(len(res["citations"]) > 0)

    # Scenario 3: Create a simple LJ liquid simulation
    def test_scenario_03_create_lj_simulation(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "Create a simple Lennard-Jones liquid simulation")
        self.assertEqual(res["intent"], "GENERATE_SCRIPT")
        self.assertIsNotNone(res["script"])
        self.assertIn("units           lj", res["script"])
        self.assertTrue(res["validation"]["valid"])
        self.assertTrue(res["requires_confirmation"])

    # Scenario 4: Create an NVT simulation
    def test_scenario_04_create_nvt_simulation(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "Simulate melting of aluminum using an NVT ensemble")
        self.assertEqual(res["intent"], "GENERATE_SCRIPT")
        self.assertIsNotNone(res["script"])
        self.assertIn("units           metal", res["script"])
        self.assertIn("fix             prod all nvt", res["script"])
        self.assertTrue(res["validation"]["valid"])

    # Scenario 5: Explain pair_style eam
    def test_scenario_05_explain_eam(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "Explain pair_style eam")
        self.assertIn("eam", res["answer"].lower())
        self.assertTrue(len(res["citations"]) > 0)

    # Scenario 6: How do I calculate RDF?
    def test_scenario_06_calculate_rdf(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "What command calculates RDF?")
        self.assertIn("compute rdf", res["answer"].lower())

    # Scenario 7: Why am I getting an illegal command error?
    def test_scenario_07_illegal_command_error(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "ERROR: Illegal fix nvt command (src/modify.cpp:100)")
        self.assertEqual(res["intent"], "DIAGNOSE_ERROR")
        self.assertIn("fix", res["answer"].lower())
        self.assertTrue(len(res["citations"]) > 0)

    # Scenario 8: Generate a melting simulation
    def test_scenario_08_generate_melting(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "Generate a melting simulation for Aluminum")
        self.assertEqual(res["intent"], "GENERATE_SCRIPT")
        self.assertIn("Al_zhou.eam.alloy", res["script"])

    # Scenario 9: Explain thermo output
    def test_scenario_09_explain_thermo_output(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "Explain what thermo output and pressure fluctuations mean")
        self.assertIn("thermo", res["answer"].lower())

    # Scenario 10: Analyze this LAMMPS error (Lost atoms)
    def test_scenario_10_analyze_lost_atoms(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "My simulation crashed with: ERROR: Lost atoms: original 1000 current 992")
        self.assertEqual(res["intent"], "DIAGNOSE_ERROR")
        self.assertIn("timestep", res["answer"].lower())

    # Scenario 11: Incomplete Liquid Scientific Request
    def test_scenario_11_incomplete_scientific_request(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "I want to simulate a liquid")
        self.assertEqual(res["intent"], "GENERATE_SCRIPT")
        self.assertTrue(any(phrase in res["answer"].lower() for phrase in ["please specify", "material", "liquid system"]))

    # Scenario 12: Memory persistence
    def test_scenario_12_memory_persistence(self):
        conv_id = str(uuid.uuid4())
        self.router.process_message(conv_id, "How do I use fix nvt?")
        history = self.router.memory.get_conversation_history(conv_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["sender"], "user")
        self.assertEqual(history[1]["sender"], "assistant")

    # Scenario 13: Local Binary Inspection Safety
    def test_scenario_13_detector_safety(self):
        detection = detect_lammps()
        self.assertIn("detected", detection)
        self.assertIn("status_text", detection)

    # Scenario 14: Multi-line question with 'fix' and 'run' is NOT misrouted to REPAIR_SCRIPT
    def test_scenario_14_multiline_question_not_repaired(self):
        conv_id = str(uuid.uuid4())
        question = "I keep getting a lost atoms error.\nHow do I fix this in my aluminum run?"
        res = self.router.process_message(conv_id, question)
        self.assertNotEqual(res["intent"], "REPAIR_SCRIPT")
        self.assertEqual(res["intent"], "DIAGNOSE_ERROR")

    # Scenario 15: Tensile deformation request is cleanly rejected as out-of-scope
    def test_scenario_15_tensile_out_of_scope(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "Simulate uniaxial tensile deformation of copper under strain rate 0.001")
        self.assertEqual(res["intent"], "UNSUPPORTED_REQUEST")
        self.assertIn("out of scope", res["answer"].lower())
        self.assertIn("solid mechanics", res["answer"].lower())
        self.assertIsNone(res["script"])

    # Scenario 16: Rigid SPC/E water simulation generation
    def test_scenario_16_water_liquid_simulation(self):
        conv_id = str(uuid.uuid4())
        res = self.router.process_message(conv_id, "Generate a simulation of water at 300 K in NVT ensemble")
        self.assertEqual(res["intent"], "GENERATE_SCRIPT")
        self.assertIsNotNone(res["script"])
        self.assertIn("units           real", res["script"])
        self.assertIn("fix             rigidH2O all shake", res["script"])
        self.assertTrue(res["validation"]["valid"])

if __name__ == "__main__":
    unittest.main()

