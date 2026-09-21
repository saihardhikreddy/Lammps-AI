"""Standard Library Local HTTP & REST Server (Zero Cloud Dependencies)."""
import http.server
import socketserver
import json
import urllib.parse
import re
import time
import uuid
import os
from pathlib import Path
from typing import Dict, Any

from app.config import HOST, PORT, GENERATED_DIR
from app.chatbot.router import ChatbotRouter
from app.lammps.detector import detect_lammps
from app.lammps.runner import SimulationRunner
from app.lammps.parser import ThermoParser

router = ChatbotRouter()
runner = SimulationRunner()
thermo_parser = ThermoParser()
STATIC_DIR = Path(__file__).parent / "static"

class LocalAssistantHandler(http.server.SimpleHTTPRequestHandler):
    """Zero-dependency HTTP request handler for local web UI and REST API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def _validate_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        allowed = {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"}
        return origin.rstrip('/') in allowed

    def do_POST(self):
        if not self._validate_origin():
            return self._send_json({"error": "Forbidden Origin"}, 403)

        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length > 0 else "{}"
        
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        try:
            if parsed.path == "/api/chat":
                conv_id = data.get("conversation_id", "")
                message = data.get("message", "")
                response = router.process_message(conv_id, message)
                self._send_json(response)

            elif parsed.path == "/api/run":
                # Security Confirmation Gate: requires explicit invocation
                script_content = data.get("script", "")
                raw_run_id = data.get("run_id")
                if not raw_run_id or not isinstance(raw_run_id, str):
                    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
                else:
                    run_id = raw_run_id.strip()

                if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
                    return self._send_json({"error": "Invalid run_id format"}, 400)

                gen_dir_resolved = GENERATED_DIR.resolve()
                gen_dir_resolved.mkdir(parents=True, exist_ok=True)
                script_path = (GENERATED_DIR / f"{run_id}.in").resolve()
                if not script_path.is_relative_to(gen_dir_resolved):
                    return self._send_json({"error": "Invalid run_id path traversal detected"}, 400)

                script_path.write_text(script_content, encoding="utf-8")

                exec_result = runner.run_script(script_path, run_id)
                if exec_result.get("log_file"):
                    thermo_data = thermo_parser.parse_log(exec_result["log_file"])
                    exec_result["thermo"] = thermo_data
                    
                    # Save to database memory
                    router.memory.save_simulation_run(
                        run_id=run_id,
                        conv_id=data.get("conversation_id", "default"),
                        script=script_content,
                        ret_code=exec_result.get("returncode", -1),
                        runtime=exec_result.get("runtime_seconds", 0.0),
                        summary=thermo_data.get("summary", {})
                    )

                self._send_json(exec_result)

            elif parsed.path == "/api/status":
                detection = detect_lammps()
                status_info = {
                    "lammps": detection,
                    "offline": True,
                    "external_api_disabled": True,
                    "indexed_documents": len(router.retriever.chunks),
                    "indexed_examples": len(router.retriever.examples),
                    "workspace_active": router.workspace_indexer.is_active(),
                    "workspace_name": router.workspace_indexer.workspace_name,
                    "workspace_files_count": len(router.workspace_indexer.files_indexed),
                    "status_text": detection["status_text"]
                }
                self._send_json(status_info)

            elif parsed.path == "/api/history":
                conv_id = data.get("conversation_id", "")
                history = router.memory.get_conversation_history(conv_id) if conv_id else []
                self._send_json({"history": history})

            elif parsed.path == "/api/project/open":
                folder_path = data.get("folder_path", "").strip()
                if not folder_path:
                    # Default to current working directory
                    folder_path = os.getcwd()
                res = router.open_workspace(folder_path)
                self._send_json(res)

            elif parsed.path == "/api/project/search":
                query = data.get("query", "").strip()
                results = router.workspace_indexer.search_workspace(query, top_k=6)
                formatted_hits = []
                for chunk, score in results:
                    formatted_hits.append({
                        "file_path": chunk.rel_path,
                        "filename": chunk.filename,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "block_type": chunk.block_type,
                        "score": round(score, 3),
                        "snippet": chunk.content[:400]
                    })
                self._send_json({"query": query, "results": formatted_hits})

            elif parsed.path == "/api/project/read":
                rel_path = data.get("rel_path", "").strip()
                content = router.workspace_indexer.read_workspace_file(rel_path)
                if content is not None:
                    self._send_json({"rel_path": rel_path, "content": content, "lines": len(content.splitlines())})
                else:
                    self._send_json({"error": f"Could not read file: {rel_path}"}, 404)

            else:
                self.send_error(404, "Endpoint not found")

        except Exception as ex:
            self._send_json({"error": f"Internal Server Error: {str(ex)}"}, 500)

    def do_GET(self):
        if not self._validate_origin():
            return self._send_json({"error": "Forbidden Origin"}, 403)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/conversations":
            convs = router.memory.list_conversations()
            self._send_json({"conversations": convs})
        elif parsed.path == "/api/project/status":
            summary = router.workspace_indexer.get_workspace_summary()
            self._send_json({
                "active": router.workspace_indexer.is_active(),
                "name": router.workspace_indexer.workspace_name,
                "path": str(router.workspace_indexer.workspace_root or ""),
                "summary": summary
            })
        elif parsed.path == "/api/project/tree":
            tree = router.workspace_indexer.get_workspace_tree()
            self._send_json({"tree": tree})
        else:
            # Serve static files (HTML, CSS, JS)
            super().do_GET()

    def _send_json(self, payload: Dict[str, Any], status: int = 200):
        out = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Multi-threaded HTTP server so simulation runs don't block other requests."""
    daemon_threads = True
    allow_reuse_address = True

def start_server():
    """Starts the local HTTP server."""
    with ThreadedHTTPServer((HOST, PORT), LocalAssistantHandler) as httpd:
        print("=" * 65)
        print(f"  LAMMPS Research Assistant Server Started")
        print(f"  Local URL: http://{HOST}:{PORT}")
        print(f"  Operational Mode: 100% OFFLINE / LOCAL")
        print(f"  Project Workspace RAG: READY")
        print(f"  External APIs: DISABLED (No Remote Calls)")
        print("=" * 65)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down LAMMPS Assistant gracefully.")
            httpd.server_close()
