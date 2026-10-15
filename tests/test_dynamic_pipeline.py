"""Unit and Integration Tests for Dynamic Parameter Extraction and Local LLM Pipeline."""
import unittest
from unittest.mock import MagicMock, patch
from app.generation.intent import IntentExtractor, SimulationParameters
from app.chatbot.router import ChatbotRouter

class TestDynamicPipeline(unittest.TestCase):
    def setUp(self):
        self.extractor = IntentExtractor()
        self.router = ChatbotRouter()
        # Default mock: disable live API calls during unit tests
        self.router.gemini_client.is_available = lambda: False
        self.router.local_llm.is_available = lambda: False

    def test_custom_temperature_never_overridden(self):
        """Verify that user-requested temperatures (e.g. 2500 K) are NOT overridden to 1828 K."""
        params = self.extractor.extract_structured_parameters("Simulate molten nickel at 2500 K using NVT")
        self.assertEqual(params.material, "nickel")
        self.assertEqual(params.target_temperature, 2500.0)
        self.assertTrue(params.user_temperature_specified)
        self.assertNotEqual(params.target_temperature, 1828.0)

    def test_atom_count_and_dump_interval_extraction(self):
        """Verify dynamic extraction of atom counts, dump intervals, and quench rates."""
        text = "Simulate molten copper with 8000 atoms at 1500 K, dump every 250 steps, quench rate 1e12 K/s"
        params = self.extractor.extract_structured_parameters(text)
        self.assertEqual(params.material, "copper")
        self.assertEqual(params.atom_count, 8000)
        self.assertEqual(params.target_temperature, 1500.0)
        self.assertEqual(params.dump_interval, 250)
        self.assertEqual(params.quench_rate, 1e12)

    def test_quench_range_extraction(self):
        """Verify extraction of temperature ranges (from T1 to T2)."""
        text = "Cool liquid aluminum from 1200 K to 500 K with cooling rate 0.5 K/ps"
        params = self.extractor.extract_structured_parameters(text)
        self.assertEqual(params.start_temperature, 1200.0)
        self.assertEqual(params.target_temperature, 500.0)
        self.assertEqual(params.simulation_type, "quench")
        self.assertTrue(params.user_temperature_specified)

    MOCK_LLM_SCRIPT_REPLY = (
        "Here is a script for liquid mercury:\n\n"
        "```lammps\n"
        "units metal\n"
        "atom_style atomic\n"
        "boundary p p p\n"
        "lattice sc 3.0\n"
        "region box block 0 4 0 4 0 4\n"
        "create_box 1 box\n"
        "create_atoms 1 box\n"
        "mass 1 200.59\n"
        "pair_style lj/cut 8.0\n"
        "pair_coeff 1 1 0.05 2.9\n"
        "velocity all create 300 1234\n"
        "timestep 0.001\n"
        "fix 1 all nvt temp 300 300 0.1\n"
        "run 1000\n"
        "```\n"
    )

    def test_supported_material_never_routed_to_gemini(self):
        """Script requests for supported liquids always use the validated templates."""
        self.router.gemini_client.is_available = lambda: True
        self.router.gemini_client.generate_with_diagnostics = MagicMock(return_value=("irrelevant", None))

        res = self.router.process_message("test_conv", "Simulate molten nickel at 2500 K with 8000 atoms")

        self.router.gemini_client.generate_with_diagnostics.assert_not_called()
        self.assertIn("Deterministic Template", res["source"])
        self.assertIn("pair_style      eam\n", res["script"])
        self.assertIn("temp 2500.0 2500.0", res["script"])
        self.assertTrue(res["validation"]["valid"])

    def test_gemini_script_for_unsupported_system_is_labelled_unverified(self):
        self.router.gemini_client.is_available = lambda: True
        self.router.gemini_client.generate_with_diagnostics = MagicMock(return_value=(self.MOCK_LLM_SCRIPT_REPLY, None))

        res = self.router.process_message("test_conv", "Write a script for liquid mercury at 300 K")

        self.router.gemini_client.generate_with_diagnostics.assert_called_once()
        self.assertIn("Cloud Gemini", res["source"])
        self.assertTrue(res.get("llm_generated"))
        self.assertIn("Unverified script", res["answer"])
        self.assertIn("mass 1 200.59", res["script"])

    def test_gemini_error_on_unsupported_script_request_is_reported(self):
        self.router.gemini_client.is_available = lambda: True
        error_detail = "Invalid Gemini API Key. Please verify your GEMINI_API_KEY."
        self.router.gemini_client.generate_with_diagnostics = MagicMock(return_value=(None, error_detail))

        res = self.router.process_message("test_conv", "Write a script for liquid mercury at 300 K")

        self.assertIn(error_detail, res["answer"])
        self.assertIsNone(res["script"])
        self.assertIn("Supported:", res["answer"])

    def test_local_llm_script_is_labelled_unverified(self):
        self.router.gemini_client.is_available = lambda: False
        self.router.local_llm.is_available = lambda: True
        self.router.local_llm.generate_with_diagnostics = MagicMock(return_value=(self.MOCK_LLM_SCRIPT_REPLY, None))

        res = self.router.process_message("test_conv", "Write a script for liquid mercury at 300 K")

        self.router.local_llm.generate_with_diagnostics.assert_called_once()
        self.assertIn("Local LLM", res["source"])
        self.assertTrue(res.get("llm_generated"))
        self.assertIn("Unverified script", res["answer"])

    def test_router_deterministic_fallback_when_all_llms_offline(self):
        """Verify clean fallback when both Cloud Gemini and Local LLM are offline."""
        self.router.gemini_client.is_available = lambda: False
        self.router.local_llm.is_available = lambda: False

        res = self.router.process_message("test_conv", "Simulate molten nickel at 1800 K")

        self.assertIn("Deterministic Template", res["source"])
        self.assertIsNotNone(res["script"])
        self.assertTrue(res["validation"]["valid"])

if __name__ == "__main__":
    unittest.main()
