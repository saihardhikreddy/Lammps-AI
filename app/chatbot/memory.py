"""Local SQLite Conversation and Simulation History Persistence."""
import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import DB_PATH

class ConversationMemory:
    """Stores local conversation threads, generated scripts, and simulation execution runs."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    title TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT,
                    sender TEXT,
                    content TEXT,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulation_runs (
                    run_id TEXT PRIMARY KEY,
                    conversation_id TEXT,
                    script_text TEXT,
                    return_code INTEGER,
                    runtime_seconds REAL,
                    summary_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id)")
            conn.commit()
        finally:
            conn.close()

    def save_turn(self, conv_id: str, user_msg: str, bot_payload: Dict[str, Any]):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO conversations (id, title) VALUES (?, ?)", (conv_id, user_msg[:45]))
            cursor.execute("INSERT INTO messages (conversation_id, sender, content, metadata_json) VALUES (?, 'user', ?, '{}')", (conv_id, user_msg))
            cursor.execute(
                "INSERT INTO messages (conversation_id, sender, content, metadata_json) VALUES (?, 'assistant', ?, ?)",
                (conv_id, bot_payload.get("answer", ""), json.dumps(bot_payload))
            )
            conn.commit()
        finally:
            conn.close()

    def save_simulation_run(self, run_id: str, conv_id: str, script: str, ret_code: int, runtime: float, summary: Dict[str, Any]):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO simulation_runs 
                (run_id, conversation_id, script_text, return_code, runtime_seconds, summary_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (run_id, conv_id, script, ret_code, runtime, json.dumps(summary)))
            conn.commit()
        finally:
            conn.close()

    def get_conversation_history(self, conv_id: str) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sender, content, metadata_json, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC",
                (conv_id,)
            )
            rows = cursor.fetchall()
            return [
                {
                    "sender": r[0],
                    "content": r[1],
                    "metadata": json.loads(r[2]) if r[2] else {},
                    "timestamp": r[3]
                }
                for r in rows
            ]
        finally:
            conn.close()

    def list_conversations(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, created_at FROM conversations ORDER BY created_at DESC, id DESC LIMIT 30")
            rows = cursor.fetchall()
            return [{"id": r[0], "title": r[1], "created_at": r[2]} for r in rows]
        finally:
            conn.close()

