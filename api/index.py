"""Vercel Serverless Function Adapter for LAMMPS AI Assistant.
Routes all /api/* requests to the Python RAG and Physics engines.
"""
import sys
import os
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.chatbot.router import ChatbotRouter
from app.lammps.runner import SimulationRunner
from app.lammps.parser import ThermoParser

# Initialize engines
router = ChatbotRouter()
runner = SimulationRunner()
thermo_parser = ThermoParser()
workspace_indexer = router.workspace_indexer

class handler(BaseHTTPRequestHandler):
    """Vercel Serverless Request Handler."""

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            from app.lammps.detector import detect_lammps
            detection = detect_lammps()
            self._send_json({
                "status": "online",
                "environment": "Vercel Serverless Cloud",
                "lammps": detection,
                "offline": True,
                "indexed_documents": len(router.retriever.chunks),
                "workspace": workspace_indexer.get_workspace_summary()
            })
        elif path == "/api/project/status":
            self._send_json(workspace_indexer.get_workspace_summary())
        elif path == "/api/project/tree":
            self._send_json(workspace_indexer.get_workspace_tree())
        else:
            self._send_json({"error": f"Route not found: {path}"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(body_raw) if body_raw else {}
        except Exception:
            data = {}

        try:
            if path == "/api/chat":
                conv_id = data.get("conversation_id", "")
                message = data.get("message", "")
                response = router.process_message(conv_id, message)
                self._send_json(response)

            elif path == "/api/run":
                script_content = data.get("script", "")
                import uuid
                run_id = f"vercel_run_{uuid.uuid4().hex[:8]}"
                tmp_dir = Path("/tmp") if os.path.exists("/tmp") else (ROOT_DIR / "data" / "runs")
                tmp_dir.mkdir(parents=True, exist_ok=True)
                script_path = tmp_dir / f"{run_id}.in"
                script_path.write_text(script_content, encoding="utf-8")

                result = runner.run_script(script_path, run_id)
                if result.get("log_file") and Path(result["log_file"]).exists():
                    log_text = Path(result["log_file"]).read_text(encoding="utf-8", errors="replace")
                    parsed_thermo = thermo_parser.parse_log_text(log_text)
                    result["thermo"] = parsed_thermo

                self._send_json(result)

            elif path == "/api/project/open":
                folder_path = data.get("folder_path", str(ROOT_DIR))
                summary = workspace_indexer.open_workspace(folder_path)
                self._send_json({"success": True, "summary": summary})

            elif path == "/api/project/search":
                query = data.get("query", "")
                results = workspace_indexer.search_workspace(query)
                self._send_json({"query": query, "results": results})

            elif path == "/api/project/read":
                rel_path = data.get("rel_path", "")
                file_data = workspace_indexer.read_workspace_file(rel_path)
                self._send_json(file_data)

            else:
                self._send_json({"error": f"Endpoint not found: {path}"}, 404)

        except Exception as e:
            self._send_json({"error": str(e)}, 500)
