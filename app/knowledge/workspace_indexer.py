"""Project-Level Codebase RAG and Workspace Indexer.

Recursively indexes local project folders (LAMMPS scripts, data topologies, Python pipelines,
potentials, logs, markdown/text notes), builds semantic code chunks with line ranges,
and provides multi-file retrieval for the local LLM and user search.
"""
import os
import re
import math
import sqlite3
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

@dataclass
class WorkspaceFileChunk:
    chunk_id: str
    file_path: str
    rel_path: str
    filename: str
    file_ext: str
    start_line: int
    end_line: int
    block_type: str
    content: str
    keywords: List[str] = field(default_factory=list)
    line_count: int = 0


class WorkspaceProjectIndexer:
    """Manages indexing, AST chunking, semantic search, and file tree exploration for local project folders."""

    SUPPORTED_EXTENSIONS = {
        ".in", ".lmp", ".lammps",       # LAMMPS simulation scripts
        ".data", ".dat", ".struct",     # Atomic coordinate/topology data
        ".py",                          # Python scripts / analysis pipelines
        ".eam", ".tersoff", ".sw",      # Potential files
        ".ff", ".params",               # Force field parameters
        ".md", ".txt", ".rst",          # Documentation & notes
        ".log", ".out",                 # Simulation logs & console dumps
        ".json", ".yaml", ".yml"        # Simulation configurations
    }

    EXCLUDED_DIRS = {
        ".git", ".svn", ".hg", "__pycache__", ".pytest_cache",
        "node_modules", ".venv", "venv", "env", "dist", "build",
        ".gemini", ".idea", ".vscode"
    }

    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB per file max

    def __init__(self, db_path: Optional[Path] = None):
        self.workspace_root: Optional[Path] = None
        self.workspace_name: str = ""
        self.chunks: List[WorkspaceFileChunk] = []
        self.files_indexed: List[Dict[str, Any]] = []
        self.db_path = db_path
        self._doc_freq: Dict[str, int] = {}
        self._total_docs = 0

    def is_active(self) -> bool:
        """Returns True if a valid workspace project is currently loaded."""
        return self.workspace_root is not None and bool(self.chunks)

    def open_workspace(self, folder_path: str) -> Dict[str, Any]:
        """Scans, parses, and indexes a local project directory."""
        p = Path(folder_path).resolve()
        if not p.exists() or not p.is_dir():
            return {
                "success": False,
                "error": f"Directory does not exist: {folder_path}"
            }

        self.workspace_root = p
        self.workspace_name = p.name
        self.chunks.clear()
        self.files_indexed.clear()
        self._doc_freq.clear()

        # Walk directory
        for root, dirs, files in os.walk(p):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS and not d.startswith('.')]

            for f in files:
                ext = Path(f).suffix.lower()
                if ext in self.SUPPORTED_EXTENSIONS or f.lower().startswith("in.") or f.lower().startswith("data."):
                    full_path = Path(root) / f
                    try:
                        size = full_path.stat().st_size
                        if size > self.MAX_FILE_SIZE_BYTES:
                            continue
                        self._index_single_file(full_path)
                    except Exception:
                        continue

        # Compute document frequencies for BM25-style scoring
        self._total_docs = len(self.chunks)
        for chunk in self.chunks:
            unique_tokens = set(self._tokenize(chunk.content))
            for tok in unique_tokens:
                self._doc_freq[tok] = self._doc_freq.get(tok, 0) + 1

        return {
            "success": True,
            "workspace_path": str(self.workspace_root),
            "workspace_name": self.workspace_name,
            "files_count": len(self.files_indexed),
            "chunks_count": len(self.chunks),
            "summary": self.get_workspace_summary()
        }

    def _index_single_file(self, file_path: Path):
        """Chunks and indexes an individual project file."""
        try:
            rel_path = file_path.relative_to(self.workspace_root).as_posix()
        except ValueError:
            rel_path = file_path.name

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except Exception:
            return

        total_lines = len(lines)
        ext = file_path.suffix.lower()
        file_info = {
            "filename": file_path.name,
            "rel_path": rel_path,
            "ext": ext,
            "line_count": total_lines,
            "size_bytes": file_path.stat().st_size
        }
        self.files_indexed.append(file_info)

        # Chunk file logically
        chunk_size = 35  # lines per chunk
        overlap = 10     # line overlap

        if total_lines <= chunk_size + 10:
            content = "".join(lines)
            chunk = WorkspaceFileChunk(
                chunk_id=f"{rel_path}:1-{total_lines}",
                file_path=str(file_path),
                rel_path=rel_path,
                filename=file_path.name,
                file_ext=ext,
                start_line=1,
                end_line=total_lines,
                block_type=self._detect_block_type(content, ext),
                content=content,
                keywords=self._extract_keywords(content),
                line_count=total_lines
            )
            self.chunks.append(chunk)
        else:
            step = chunk_size - overlap
            for start in range(0, total_lines, step):
                end = min(start + chunk_size, total_lines)
                chunk_lines = lines[start:end]
                content = "".join(chunk_lines)
                chunk = WorkspaceFileChunk(
                    chunk_id=f"{rel_path}:{start+1}-{end}",
                    file_path=str(file_path),
                    rel_path=rel_path,
                    filename=file_path.name,
                    file_ext=ext,
                    start_line=start + 1,
                    end_line=end,
                    block_type=self._detect_block_type(content, ext),
                    content=content,
                    keywords=self._extract_keywords(content),
                    line_count=len(chunk_lines)
                )
                self.chunks.append(chunk)
                if end >= total_lines:
                    break

    def _detect_block_type(self, text: str, ext: str) -> str:
        """Determines the semantic category of code chunk."""
        t_low = text.lower()
        if ext in {".in", ".lmp", ".lammps"} or "in." in ext:
            if "pair_style" in t_low or "pair_coeff" in t_low:
                return "Potential & Interatomic Physics"
            if "fix " in t_low and ("nvt" in t_low or "npt" in t_low or "nve" in t_low):
                return "Ensemble & Time Integration"
            if "create_box" in t_low or "create_atoms" in t_low or "read_data" in t_low:
                return "System Initialization & Geometry"
            if "compute " in t_low or "dump " in t_low or "thermo" in t_low:
                return "Diagnostics & Output Telemetry"
            return "LAMMPS Script Block"
        elif ext == ".py":
            if "class " in text:
                return "Python Class Definition"
            if "def " in text:
                return "Python Function"
            return "Python Code Block"
        elif ext in {".data", ".dat", ".struct"}:
            return "Atom Topology & Coordinates"
        elif ext in {".eam", ".tersoff", ".sw", ".ff"}:
            return "Force Field Parameter Table"
        elif ext in {".md", ".txt", ".rst"}:
            return "Documentation / Notes"
        return "Workspace Source File"

    def _tokenize(self, text: str) -> List[str]:
        return [w.lower() for w in re.findall(r'[A-Za-z0-9_]+', text) if len(w) > 1]

    def _extract_keywords(self, text: str) -> List[str]:
        tokens = self._tokenize(text)
        stopwords = {"the", "and", "for", "with", "this", "that", "from", "all", "are", "have"}
        freq = {}
        for t in tokens:
            if t not in stopwords and len(t) > 2:
                freq[t] = freq.get(t, 0) + 1
        sorted_k = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [k[0] for k in sorted_k[:10]]

    def search_workspace(self, query: str, top_k: int = 4) -> List[Tuple[WorkspaceFileChunk, float]]:
        """Performs multi-signal BM25 + keyword relevance search across indexed project files."""
        if not self.chunks:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored = []
        q_lower = query.lower()

        for chunk in self.chunks:
            score = 0.0
            content_lower = chunk.content.lower()

            # 1. Filename match boost
            if chunk.filename.lower() in q_lower or any(tok in chunk.filename.lower() for tok in query_tokens):
                score += 3.0

            # 2. Exact phrase bonus
            if q_lower in content_lower:
                score += 2.5

            # 3. BM25-style token matching
            chunk_tokens = self._tokenize(chunk.content)
            chunk_len = len(chunk_tokens)
            if chunk_len == 0:
                continue

            for tok in query_tokens:
                c_cnt = chunk_tokens.count(tok)
                if c_cnt > 0:
                    df = self._doc_freq.get(tok, 1)
                    idf = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1.0)
                    tf = (c_cnt * 2.2) / (c_cnt + 1.2 * (0.25 + 0.75 * (chunk_len / 50.0)))
                    score += idf * tf

            # 4. Keyword overlap
            kw_overlap = len(set(query_tokens) & set(chunk.keywords))
            score += kw_overlap * 0.8

            if score > 0.1:
                scored.append((chunk, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get_workspace_tree(self) -> Dict[str, Any]:
        """Builds a hierarchical JSON tree of the project workspace directory."""
        if not self.workspace_root:
            return {}

        tree = {
            "name": self.workspace_name,
            "path": str(self.workspace_root),
            "type": "directory",
            "children": []
        }

        # Build directory structure from indexed files
        dir_map: Dict[str, Dict[str, Any]] = {"": tree}

        for f in self.files_indexed:
            rel = f["rel_path"]
            parts = rel.split('/')
            
            # Ensure parent directories exist in tree
            curr_path = ""
            for p in parts[:-1]:
                parent_path = curr_path
                curr_path = f"{curr_path}/{p}" if curr_path else p
                if curr_path not in dir_map:
                    node = {
                        "name": p,
                        "path": curr_path,
                        "type": "directory",
                        "children": []
                    }
                    dir_map[curr_path] = node
                    dir_map[parent_path]["children"].append(node)

            # Add file node
            parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
            file_node = {
                "name": f["filename"],
                "path": rel,
                "type": "file",
                "ext": f["ext"],
                "line_count": f["line_count"],
                "size_bytes": f["size_bytes"]
            }
            dir_map[parent_path]["children"].append(file_node)

        return tree

    def get_workspace_summary(self) -> Dict[str, Any]:
        """Returns a high-level computational summary of the project workspace."""
        if not self.files_indexed:
            return {}

        ext_counts = {}
        lammps_scripts = []
        potentials = []
        data_files = []

        for f in self.files_indexed:
            ext = f["ext"]
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            if ext in {".in", ".lmp", ".lammps"} or "in." in f["filename"]:
                lammps_scripts.append(f["rel_path"])
            elif ext in {".eam", ".tersoff", ".sw", ".ff"}:
                potentials.append(f["rel_path"])
            elif ext in {".data", ".dat", ".struct"}:
                data_files.append(f["rel_path"])

        return {
            "root_name": self.workspace_name,
            "root_path": str(self.workspace_root),
            "total_files": len(self.files_indexed),
            "total_chunks": len(self.chunks),
            "extension_counts": ext_counts,
            "lammps_scripts": lammps_scripts,
            "potential_files": potentials,
            "data_files": data_files
        }

    def read_workspace_file(self, rel_path: str) -> Optional[str]:
        """Reads a specific file from the workspace root safely."""
        if not self.workspace_root:
            return None
        target = (self.workspace_root / rel_path).resolve()
        try:
            # Ensure target is strictly inside workspace_root
            rel = target.relative_to(self.workspace_root.resolve())
            # Never hand out hidden files or credentials (.env, .git/*, keys), only file types
            # the indexer itself would read
            if any(part.startswith(".") for part in rel.parts):
                return None
            name = target.name.lower()
            if any(tok in name for tok in ("secret", "credential", "id_rsa", "id_ed25519")) or \
                    target.suffix.lower() in (".pem", ".key", ".p12", ".pfx", ".db", ".sqlite"):
                return None
            if not (target.suffix.lower() in self.SUPPORTED_EXTENSIONS or name.startswith(("in.", "data."))):
                return None
            if target.exists() and target.is_file():
                with open(target, "r", encoding="utf-8", errors="replace") as fh:
                    return fh.read()
        except Exception:
            return None
        return None
