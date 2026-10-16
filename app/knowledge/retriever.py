"""Local Offline Multi-Signal Knowledge Retriever."""
import re
import math
from typing import List, Tuple, Dict, Any, Optional
from app.knowledge.schema import DocChunk, ExampleChunk
from app.knowledge.builtins import BUILTIN_COMMANDS, BUILTIN_GUIDES, BUILTIN_EXAMPLES
from app.knowledge.indexer import LocalIndexer

class LocalKnowledgeRetriever:
    """Dependency-free local retrieval engine with transparent, explainable multi-signal scoring."""

    def __init__(self, indexer: Optional[LocalIndexer] = None):
        self.indexer = indexer or LocalIndexer()
        self.chunks: List[DocChunk] = []
        self.examples: List[ExampleChunk] = BUILTIN_EXAMPLES
        self._initialize_corpus()

    def _initialize_corpus(self):
        # 1. Load built-in command reference
        for cmd, info in BUILTIN_COMMANDS.items():
            content = f"Command: {cmd}\nSyntax: {info['syntax']}\nDescription: {info['description']}"
            if "details" in info:
                content += f"\nDetails: {info['details']}"
            if "styles" in info and info["styles"]:
                content += f"\nSupported Styles: {', '.join(info['styles'])}"
            
            chunk = DocChunk(
                chunk_id=f"cmd_{cmd.replace(' ', '_').replace('/', '_')}",
                source_path=f"LAMMPS Manual → Commands → {cmd}",
                doc_type="command",
                section=info.get("section", "Commands"),
                subsection=cmd,
                command_name=cmd,
                title=f"LAMMPS command: {cmd}",
                content=content,
                keywords=info.get("keywords", cmd.split())
            )
            self.chunks.append(chunk)

        # 2. Load built-in guides & error references
        self.chunks.extend(BUILTIN_GUIDES)

        # 3. Load indexed user documents if any
        user_chunks = self.indexer.load_all_chunks()
        if user_chunks:
            self.chunks.extend(user_chunks)

    def _tokenize(self, text: str) -> List[str]:
        return [w.lower() for w in re.findall(r'[A-Za-z0-9_]+', text) if len(w) > 1]

    def search(self, query: str, top_k: int = 4) -> List[Tuple[DocChunk, float, Dict[str, float]]]:
        """Search documentation with transparent multi-signal weighted scoring."""
        query_tokens = self._tokenize(query)
        scored_results = []
        query_lower = query.lower()

        # Detect command candidates in query
        command_candidates = self._detect_commands_in_query(query_lower)

        for chunk in self.chunks:
            # 1. Semantic keyword score
            chunk_tokens = self._tokenize(f"{chunk.title} {chunk.content} {' '.join(chunk.keywords)}")
            overlap = sum(1 for t in query_tokens if t in chunk_tokens)
            keyword_score = overlap / max(len(query_tokens), 1)

            # 2. Command match score
            command_score = 0.0
            if chunk.command_name:
                cmd_norm = chunk.command_name.lower()
                if cmd_norm in command_candidates:
                    command_score = 1.0
                elif any(p in query_lower for p in cmd_norm.split()):
                    command_score = 0.6

            # 3. Section match score
            section_score = 0.0
            if chunk.section.lower() in query_lower or chunk.subsection.lower() in query_lower:
                section_score = 1.0

            # 4. Example match score
            example_score = 0.0
            if any(w in query_lower for w in ["example", "how to", "sample", "script", "template", "code"]):
                example_score = 0.8

            # Formula: 0.40 * semantic_keyword + 0.25 * command_match + 0.20 * section_match + 0.15 * example_match
            final_score = (
                0.40 * keyword_score +
                0.25 * command_score +
                0.20 * section_score +
                0.15 * example_score
            )

            if final_score > 0.05:
                breakdown = {
                    "keyword_score": round(keyword_score, 3),
                    "command_score": round(command_score, 3),
                    "section_score": round(section_score, 3),
                    "example_score": round(example_score, 3),
                    "final_score": round(final_score, 3)
                }
                scored_results.append((chunk, final_score, breakdown))

        scored_results.sort(key=lambda x: x[1], reverse=True)
        return scored_results[:top_k]

    def _detect_commands_in_query(self, query_lower: str) -> List[str]:
        detected = []
        for cmd in BUILTIN_COMMANDS.keys():
            if cmd in query_lower:
                detected.append(cmd)
        return detected

    def find_relevant_example(self, topic_query: str) -> Optional[ExampleChunk]:
        """Finds the most relevant official example for a simulation task."""
        query_lower = topic_query.lower()
        best_ex = None
        best_score = 0

        for ex in self.examples:
            score = 0
            if ex.topic.lower() in query_lower:
                score += 5
            for mat in ex.materials:
                if mat.lower() in query_lower:
                    score += 4
            for cmd in ex.commands_used:
                if cmd.lower() in query_lower:
                    score += 2
            if score > best_score:
                best_score = score
                best_ex = ex

        return best_ex if best_score > 0 else None

