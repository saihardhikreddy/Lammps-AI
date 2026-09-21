"""Unit tests for WorkspaceProjectIndexer and Codebase RAG."""
import unittest
import tempfile
import shutil
from pathlib import Path
from app.knowledge.workspace_indexer import WorkspaceProjectIndexer

class TestWorkspaceProjectIndexer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

        # Create dummy project structure
        sim_dir = self.root / "simulations"
        sim_dir.mkdir(parents=True, exist_ok=True)

        pot_dir = self.root / "potentials"
        pot_dir.mkdir(parents=True, exist_ok=True)

        # 1. in.melt
        (sim_dir / "in.melt").write_text(
            "# Melting simulation of Copper\n"
            "units metal\n"
            "boundary p p p\n"
            "atom_style atomic\n"
            "lattice fcc 3.615\n"
            "region box block 0 10 0 10 0 10\n"
            "create_box 1 box\n"
            "create_atoms 1 box\n"
            "pair_style eam\n"
            "pair_coeff * * ../potentials/Cu_u3.eam\n"
            "fix 1 all nvt temp 300.0 1500.0 0.1\n"
            "thermo 100\n"
            "run 10000\n",
            encoding="utf-8"
        )

        # 2. Cu_u3.eam
        (pot_dir / "Cu_u3.eam").write_text("# EAM potential table for Copper", encoding="utf-8")

        # 3. analyze.py
        (self.root / "analyze.py").write_text(
            "import numpy as np\n"
            "def calculate_diffusion(msd):\n"
            "    return np.polyfit(msd[:, 0], msd[:, 1], 1)[0] / 6.0\n",
            encoding="utf-8"
        )

        # 4. README.md
        (self.root / "README.md").write_text(
            "# High-Temperature Copper Melting Project\n"
            "This project models the phase transition of single-crystal Copper.\n",
            encoding="utf-8"
        )

        self.indexer = WorkspaceProjectIndexer()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_open_workspace(self):
        res = self.indexer.open_workspace(str(self.root))
        self.assertTrue(res["success"])
        self.assertEqual(res["files_count"], 4)
        self.assertTrue(res["chunks_count"] >= 4)
        self.assertTrue(self.indexer.is_active())

    def test_workspace_summary(self):
        self.indexer.open_workspace(str(self.root))
        summary = self.indexer.get_workspace_summary()
        self.assertEqual(summary["total_files"], 4)
        self.assertIn("simulations/in.melt", summary["lammps_scripts"])
        self.assertIn("potentials/Cu_u3.eam", summary["potential_files"])

    def test_search_workspace(self):
        self.indexer.open_workspace(str(self.root))
        # Search for melting / copper
        results = self.indexer.search_workspace("Copper melting nvt simulation", top_k=2)
        self.assertTrue(len(results) > 0)
        top_chunk, score = results[0]
        self.assertIn("Cu", top_chunk.content)
        self.assertTrue(score > 0)
        self.assertEqual(top_chunk.filename, "in.melt")

    def test_search_python_function(self):
        self.indexer.open_workspace(str(self.root))
        results = self.indexer.search_workspace("calculate_diffusion", top_k=1)
        self.assertTrue(len(results) > 0)
        top_chunk, _ = results[0]
        self.assertEqual(top_chunk.filename, "analyze.py")
        self.assertIn("calculate_diffusion", top_chunk.content)

    def test_workspace_tree_and_read(self):
        self.indexer.open_workspace(str(self.root))
        tree = self.indexer.get_workspace_tree()
        self.assertEqual(tree["type"], "directory")
        self.assertTrue(len(tree["children"]) > 0)

        content = self.indexer.read_workspace_file("simulations/in.melt")
        self.assertIsNotNone(content)
        self.assertIn("units metal", content)

if __name__ == "__main__":
    unittest.main()
