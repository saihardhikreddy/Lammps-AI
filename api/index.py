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

WORKSPACE_DISABLED = {
    "error": "Workspace browsing is disabled in the public deployment. Run the app locally to index your own project folder."
}


class handler(BaseHTTPRequestHandler):
    """Vercel Serverless Request Handler."""

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        # Same-origin only: the static UI and this API share the deployment's origin
        self.send_response(204)
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
                "offline": not router.gemini_client.is_configured(),
                "indexed_documents": len(router.retriever.chunks),
                "workspace": workspace_indexer.get_workspace_summary()
            })
        elif path.startswith("/api/project/"):
            self._send_json(WORKSPACE_DISABLED, 403)
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

                # Serverless functions end with the response, so run synchronously. No LAMMPS
                # binary exists on Vercel: this is the labelled synthetic engine, never real data.
                result = runner.run_script(script_path, run_id, sync=True)
                if result.get("log_file") and Path(result["log_file"]).exists():
                    log_text = Path(result["log_file"]).read_text(encoding="utf-8", errors="replace")
                    parsed_thermo = thermo_parser.parse_log_text(log_text)
                    result["thermo"] = parsed_thermo

                self._send_json(result)

            elif path.startswith("/api/project/"):
                # A public deployment must never browse or read its own filesystem
                self._send_json(WORKSPACE_DISABLED, 403)

            else:
                self._send_json({"error": f"Endpoint not found: {path}"}, 404)

        except Exception as e:
            self._send_json({"error": str(e)}, 500)
