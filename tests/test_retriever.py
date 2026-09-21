"""Unit tests for LocalKnowledgeRetriever and vector/keyword matching."""
import unittest
from app.knowledge.retriever import LocalKnowledgeRetriever

class TestKnowledgeRetriever(unittest.TestCase):
    def setUp(self):
        self.retriever = LocalKnowledgeRetriever()

    def test_search_exact_command(self):
        results = self.retriever.search("fix nvt", top_k=3)
        self.assertTrue(len(results) > 0)
        top_chunk = results[0][0]
        self.assertIn("nvt", top_chunk.content.lower())

    def test_search_potential(self):
        results = self.retriever.search("eam alloy metallic potential", top_k=3)
        self.assertTrue(len(results) > 0)
        self.assertTrue(any("eam" in r[0].content.lower() for r in results))

    def test_search_rdf(self):
        results = self.retriever.search("compute rdf radial distribution function", top_k=3)
        self.assertTrue(len(results) > 0)
        self.assertTrue(any("rdf" in r[0].content.lower() for r in results))

    def test_search_python_guide(self):
        results = self.retriever.search("units metal picoseconds", top_k=3)
        self.assertTrue(len(results) > 0)

    def test_find_example(self):
        ex = self.retriever.find_relevant_example("melting of aluminum FCC")
        self.assertIsNotNone(ex)
        self.assertIn("al", ex.description.lower())
