"""Local inverted index and SQLite persistence for knowledge chunks."""
import sqlite3
import json
from pathlib import Path
from typing import List, Optional
from app.config import DB_PATH
from app.knowledge.schema import DocChunk

class LocalIndexer:
    """Manages SQLite storage and inverted search indexing for documentation chunks."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS doc_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_path TEXT,
                    doc_type TEXT,
                    section TEXT,
                    subsection TEXT,
                    command_name TEXT,
                    package_name TEXT,
                    title TEXT,
                    content TEXT,
                    keywords_json TEXT,
                    metadata_json TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_command_name ON doc_chunks(command_name);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_section ON doc_chunks(section);
            """)
            conn.commit()

    def index_chunks(self, chunks: List[DocChunk]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for c in chunks:
                cursor.execute("""
                    INSERT OR REPLACE INTO doc_chunks 
                    (chunk_id, source_path, doc_type, section, subsection, command_name, package_name, title, content, keywords_json, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c.chunk_id, c.source_path, c.doc_type, c.section, c.subsection,
                    c.command_name, c.package_name, c.title, c.content,
                    json.dumps(c.keywords), json.dumps(c.metadata)
                ))
            conn.commit()

    def load_all_chunks(self) -> List[DocChunk]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chunk_id, source_path, doc_type, section, subsection, command_name, package_name, title, content, keywords_json, metadata_json FROM doc_chunks")
            rows = cursor.fetchall()
            chunks = []
            for r in rows:
                chunks.append(DocChunk(
                    chunk_id=r[0],
                    source_path=r[1],
                    doc_type=r[2],
                    section=r[3],
                    subsection=r[4],
                    command_name=r[5],
                    package_name=r[6],
                    title=r[7],
                    content=r[8],
                    keywords=json.loads(r[9]) if r[9] else [],
                    metadata=json.loads(r[10]) if r[10] else {}
                ))
            return chunks
