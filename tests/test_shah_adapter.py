"""Unit tests for Shah Research Group MDTransport Adapter & Knowledge Integration."""
import unittest
from app.adapters.shah_adapter import ShahMDTransportAdapter
from app.knowledge.retriever import LocalKnowledgeRetriever

class TestShahMDTransportAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = ShahMDTransportAdapter()
        self.retriever = LocalKnowledgeRetriever()

    def test_generate_mdtransport_command_basic(self):
        cmd = self.adapter.generate_mdtransport_command(
            traj_file="al_melt.lammpstrj",
            species={"Al": 500},
            rcut=10.0,
            rbin=0.05
        )
        self.assertIn("mdtransport", cmd)
        self.assertIn("--lamp", cmd)
        self.assertIn("--lam_in al_melt.lammpstrj", cmd)
        self.assertIn("--species Al 500", cmd)
        self.assertIn("--rcut 10.0", cmd)
        self.assertIn("--rbin 0.05", cmd)

    def test_generate_mdtransport_command_multispecies(self):
        cmd = self.adapter.generate_mdtransport_command(
            traj_file="ionic_liquid.lammpstrj",
            species={"EMI": 250, "BF4": 250},
            analysis_mode="--lamp"
        )
        self.assertIn("--species EMI 250 BF4 250", cmd)

    def test_generate_prompt(self):
        spec = {
            "material_name": "1-Ethyl-3-methylimidazolium tetrafluoroborate",
            "simulation_type": "transport_properties",
            "temperature": 350.0,
            "species": {"EMI": 300, "BF4": 300}
        }
        prompt = self.adapter.generate_prompt(spec)
        self.assertIn("Shah Research Group Workflow", prompt)
        self.assertIn("350.0 K", prompt)
        self.assertIn("Self-Diffusion Coefficient", prompt)
        self.assertIn("MDTransport Analysis Command", prompt)

    def test_calculate_diffusion_coefficient(self):
        # 10 ps trajectory where MSD grows linearly at 60 A^2 / ps -> D = 10 A^2/ps = 1e-7 m^2/s
        time_ps = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
        msd_vals = [0.0, 120.0, 240.0, 360.0, 480.0, 600.0]
        res = self.adapter.calculate_diffusion_coefficient(time_ps, msd_vals)
        self.assertAlmostEqual(res["slope_angstrom2_ps"], 60.0, delta=1e-3)
        self.assertAlmostEqual(res["diffusion_coefficient_m2_s"], 1.0e-7, delta=1e-9)

    def test_knowledge_retrieval_shah_group(self):
        results = self.retriever.search("Shah Research Group MDTransport trajectory analysis", top_k=2)
        self.assertTrue(len(results) > 0)
        top_chunk = results[0][0]
        self.assertIn("mdtransport", top_chunk.content.lower())
        self.assertIn("shah", top_chunk.source_path.lower())

if __name__ == "__main__":
    unittest.main()
