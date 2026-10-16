"""Python Standard Library HTTP Server with Native SSE Streaming and CSRF Protection."""
import os
import re
import sys
import time
import json
import uuid
import secrets
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Dict, Any

from app import config as app_config
from app.config import HOST, PORT, GENERATED_DIR, BASE_DIR, RUNS_DIR
from app.chatbot.router import ChatbotRouter
from app.lammps.detector import detect_lammps
from app.lammps.runner import SimulationRunner, get_run_state
from app.lammps import param_scripts

# Core singletons
router = ChatbotRouter()
runner = SimulationRunner()
STATIC_DIR = Path(__file__).parent / "static"

# Cryptographically secure CSRF session token minted on server startup
SESSION_TOKEN = secrets.token_hex(24)

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
}


class LAMMPSRequestHandler(BaseHTTPRequestHandler):
    """Zero-dependency HTTP request handler for LAMMPS Research Assistant."""

    server_version = "LAMMPSAssistant/2.0"

    def _allowed_hosts(self) -> set:
        """host:port values this server answers to (uses the actual bound port)."""
        port = self.server.server_address[1] if self.server else PORT
        return {f"127.0.0.1:{port}", f"localhost:{port}", f"{HOST}:{port}".lower(), f"[::1]:{port}"}

    def _set_cors_headers(self):
        """Same-origin only: echo the Origin back solely when it is this server itself."""
        origin = (self.headers.get("Origin") or "").rstrip("/").lower()
        if origin and origin.split("://", 1)[-1] in self._allowed_hosts():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Session-Token")

    def _validate_origin(self) -> bool:
        """Rejects foreign Origin headers and foreign Host headers (DNS-rebinding defence)."""
        host = (self.headers.get("Host") or "").strip().lower()
        if host and host not in self._allowed_hosts():
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        origin_clean = origin.rstrip("/").lower()
        if not origin_clean.startswith("http://"):
            return False
        return origin_clean[len("http://"):] in self._allowed_hosts()

    def _has_valid_token(self, data: Optional[dict] = None) -> bool:
        header_token = self.headers.get("X-Session-Token")
        body_token = (data or {}).get("session_token") if isinstance(data, dict) else None
        return secrets.compare_digest(str(header_token or ""), SESSION_TOKEN) or \
            secrets.compare_digest(str(body_token or ""), SESSION_TOKEN)

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400):
        self._send_json({"error": message, "detail": message}, status=status)

    def do_OPTIONS(self):
        if not self._validate_origin():
            self._send_error_json("Forbidden: Invalid Origin", 403)
            return
        self.send_response(204)
        self._set_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── GET REQUESTS ─────────────────────────────────────────────────────────

    def do_GET(self):
        if not self._validate_origin():
            self._send_error_json("Forbidden: Invalid Origin or Host", 403)
            return
        try:
            self._dispatch_get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self._send_error_json(f"Internal server error: {type(e).__name__}: {e}", 500)

    def _dispatch_get(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # 1. Trajectory & Console SSE Stream Endpoint
        if path == "/api/run/stream":
            self._handle_run_stream(qs)
            return

        # 2. Rendered OVITO Image Endpoint
        if path == "/api/run/render":
            self._handle_run_render(qs)
            return

        # 3. Status Endpoint
        if path == "/api/status":
            self._handle_get_status(refresh=qs.get("refresh", ["0"])[0] == "1")
            return

        # 4. Conversations List
        if path == "/api/conversations":
            convs = router.memory.list_conversations()
            self._send_json({"conversations": convs})
            return

        # 5. Project Workspace Status & Tree
        if path == "/api/project/status":
            self._send_json({
                "active": router.workspace_indexer.is_active(),
                "name": router.workspace_indexer.workspace_name,
                "path": str(router.workspace_indexer.workspace_root or ""),
                "summary": router.workspace_indexer.get_workspace_summary()
            })
            return

        if path == "/api/project/tree":
            self._send_json({"tree": router.workspace_indexer.get_workspace_tree()})
            return

        # 5b. Lecturer scripts with editable variable lines (Parameter Runs tab)
        if path == "/api/param-scripts":
            if not self._has_valid_token():
                self._send_error_json("Forbidden: Invalid or missing CSRF session token", 403)
                return
            self._send_json({"scripts": param_scripts.list_scripts()})
            return

        # 6. Static Files
        self._serve_static(path)

    # ── POST REQUESTS ────────────────────────────────────────────────────────

    def do_POST(self):
        if not self._validate_origin():
            self._send_error_json("Forbidden: Invalid Origin or Host", 403)
            return
        try:
            self._dispatch_post()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self._send_error_json(f"Internal server error: {type(e).__name__}: {e}", 500)

    def _dispatch_post(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Read JSON body
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_error_json("Invalid Content-Length", 400)
            return
        if length > 5_000_000:
            self._send_error_json("Request body too large", 413)
            return
        body_raw = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else "{}"
        try:
            data = json.loads(body_raw) if body_raw else {}
        except Exception:
            self._send_error_json("Request body must be JSON", 400)
            return
        if not isinstance(data, dict):
            self._send_error_json("Request body must be a JSON object", 400)
            return

        # Every state-changing endpoint requires the per-session token minted into index.html
        if path != "/api/status" and not self._has_valid_token(data):
            self._send_error_json("Forbidden: Invalid or missing CSRF session token", 403)
            return

        # 1. Chatbot Endpoint
        if path in ("/api/chat", "/chat"):
            user_prompt = data.get("message") or data.get("prompt") or data.get("input_text") or ""
            if data.get("api_key"):
                router.set_gemini_api_key(data["api_key"])
            conv_id = data.get("conversation_id")
            res = router.process_message(conv_id, user_prompt)
            self._send_json(res)
            return

        # 2. Asynchronous Simulation Run Endpoint
        if path == "/api/run":
            self._handle_post_run(data)
            return

        # 2b. Parameter run of a lecturer script (validated values -> edited copy in the run folder)
        if path == "/api/param-scripts/run":
            self._handle_param_run(data)
            return

        # 3. Dynamic Status
        if path == "/api/status":
            self._handle_get_status()
            return

        # 3b. Deterministic template for the viewer presets
        if path == "/api/preset":
            self._handle_preset(data)
            return

        # 4. API Key Configuration
        if path == "/api/key/set":
            key = data.get("api_key", "").strip()
            model = data.get("model", "gemini-2.5-flash")
            if not key or len(key) < 10:
                self._send_error_json("Invalid API key format", 400)
                return
            if not re.fullmatch(r"[A-Za-z0-9_\-]{10,200}", key) or not re.fullmatch(r"[A-Za-z0-9_.\-]{1,80}", str(model)):
                self._send_error_json("Invalid API key or model name", 400)
                return
            router.set_gemini_api_key(key, model)
            try:
                update_env_file(app_config.ENV_FILE, {"GEMINI_API_KEY": key, "GEMINI_MODEL": model})
            except Exception:
                pass
            self._send_json({
                "success": True,
                "gemini_ready": True,
                "model": router.gemini_client.model_name,
                "message": f"Gemini API key updated with model {router.gemini_client.model_name}."
            })
            return

        # 5. Conversation Multi-turn History
        if path == "/api/history":
            conv_id = data.get("conversation_id")
            history = router.memory.get_conversation_history(conv_id) if conv_id else []
            self._send_json({"history": history})
            return

        # 6. Workspace Open, Search, Read
        if path == "/api/project/open":
            folder = (data.get("folder_path") or "").strip() or os.getcwd()
            res = router.open_workspace(folder)
            self._send_json(res)
            return

        if path == "/api/project/search":
            query = data.get("query", "")
            try:
                top_k = max(1, min(int(data.get("top_k", 6)), 50))
            except (TypeError, ValueError):
                top_k = 6
            results = router.workspace_indexer.search_workspace(query, top_k=top_k)
            hits = []
            for chunk, score in results:
                hits.append({
                    "file_path": chunk.rel_path,
                    "filename": chunk.filename,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "block_type": chunk.block_type,
                    "score": round(score, 3),
                    "snippet": chunk.content[:400]
                })
            self._send_json({"query": query, "results": hits})
            return

        if path == "/api/project/read":
            rel_p = data.get("rel_path", "")
            content = router.workspace_indexer.read_workspace_file(rel_p)
            if content is not None:
                self._send_json({"rel_path": rel_p, "content": content, "lines": len(content.splitlines())})
            else:
                self._send_error_json(f"Could not read file: {rel_p}", 404)
            return

        self._send_error_json(f"Endpoint not found: {path}", 404)

    # ── HANDLERS ─────────────────────────────────────────────────────────────

    def _handle_get_status(self, refresh: bool = False):
        detection = detect_lammps(force_refresh=refresh)
        gemini_active = router.gemini_client.is_configured()
        local_active = router.local_llm.is_available()

        self._send_json({
            "framework": "Python Standard Library (ThreadingHTTPServer)",
            "lammps": detection,
            "gemini_ready": gemini_active,
            "gemini_model": router.gemini_client.model_name,
            "llm_available": gemini_active or local_active,
            "llm_model": (f"Gemini ({router.gemini_client.model_name})" if gemini_active else (router.local_llm.model_name if local_active else None)),
            "offline": not gemini_active,
            "external_api_disabled": not gemini_active,
            "indexed_documents": len(router.retriever.chunks),
            "indexed_examples": len(router.retriever.examples),
            "workspace_active": router.workspace_indexer.is_active(),
            "workspace_name": router.workspace_indexer.workspace_name,
            "workspace_files_count": len(router.workspace_indexer.files_indexed),
            "status_text": detection["status_text"]
        })

    def _handle_preset(self, data: dict):
        """Returns a generator-built script for the trajectory-viewer presets (single source of truth)."""
        prompts = {
            "lj_benchmark": "Simulate a Lennard-Jones liquid at T* 1.44 in NVT",
            "molten_al": "Simulate molten aluminum at 1100 K in NVT",
            "water_liquid": "Simulate liquid water at 300 K in NVT",
        }
        preset = data.get("preset", "")
        if preset not in prompts:
            self._send_error_json(f"Unknown preset: {preset}", 400)
            return
        spec = router.intent_extractor.extract_intent(prompts[preset])
        gen = router.generator.generate(spec)
        self._send_json({
            "preset": preset,
            "script": gen["script"],
            "assumptions": gen["assumptions"],
            "visual_metadata": gen.get("visual_metadata"),
            "validation": router.validator.validate_static(gen["script"]),
        })

    def _handle_post_run(self, data: dict):
        """Asynchronous execution starter (CSRF token already checked in do_POST)."""
        script_content = data.get("script", "")
        if not isinstance(script_content, str) or not script_content.strip():
            self._send_error_json("Script content cannot be empty", 400)
            return

        raw_run_id = data.get("run_id")
        if not raw_run_id or not isinstance(raw_run_id, str):
            run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        else:
            run_id = raw_run_id.strip()

        # Path traversal guard: regex whitelist
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
            self._send_error_json("Invalid run_id format", 400)
            return

        gen_dir_resolved = GENERATED_DIR.resolve()
        gen_dir_resolved.mkdir(parents=True, exist_ok=True)
        script_path = (GENERATED_DIR / f"{run_id}.in").resolve()

        if not script_path.is_relative_to(gen_dir_resolved):
            self._send_error_json("Path traversal detected", 400)
            return

        script_path.write_text(script_content, encoding="utf-8")

        # Determine visual metadata if provided or infer from script
        vis_meta = data.get("visual_metadata")
        if not vis_meta:
            lower_script = script_content.lower()
            if "spc/e" in lower_script or "shake" in lower_script or "real" in lower_script:
                vis_meta = {
                    "system": "SPC/E Water",
                    "types": {
                        "1": {"name": "O", "color": "#ff4444", "radius": 1.52},
                        "2": {"name": "H", "color": "#ffffff", "radius": 1.10}
                    },
                    "box_size": [19.5, 19.5, 19.5]
                }
            elif "metal" in lower_script:
                vis_meta = {
                    "system": "Molten Metal",
                    "types": {"1": {"name": "Atom", "color": "#00f0ff", "radius": 1.43}},
                    "box_size": [16.2, 16.2, 16.2]
                }
            else:
                vis_meta = {
                    "system": "LJ Fluid",
                    "types": {"1": {"name": "Ar", "color": "#a855f7", "radius": 1.50}},
                    "box_size": [15.0, 15.0, 15.0]
                }

        # Start asynchronous execution in background worker thread
        conv_id = data.get("conversation_id", "default")
        exec_start = runner.run_script(
            script_path=script_path,
            run_id=run_id,
            visual_metadata=vis_meta,
            conversation_id=conv_id,
            sync=False
        )

        if not exec_start.get("success", False):
            self._send_error_json(exec_start.get("error", "Execution failed to initialize"), 400)
            return

        self._send_json({
            "run_id": run_id,
            "status": "running",
            "message": "Simulation started asynchronously. Stream output via /api/run/stream."
        })

    def _handle_param_run(self, data: dict):
        """Validate {file_id, params}, render the edited copy into a run folder, start the existing runner."""
        file_id = data.get("file_id")
        try:
            prepared = param_scripts.prepare(file_id if isinstance(file_id, str) else "", data.get("params") or {})
        except KeyError:
            self._send_error_json(f"Unknown parameter script: {file_id}", 404)
            return
        except param_scripts.ParamError as e:
            self._send_json({"error": "Invalid parameter values", "fields": e.errors}, status=400)
            return
        if data.get("dry_run"):
            self._send_json({"file_id": file_id, "script": prepared["text"],
                             "changed_lines": prepared["changed_lines"], "viewer": prepared["viewer"]})
            return

        run_id = f"param_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        work_dir = (RUNS_DIR / run_id).resolve()
        if not work_dir.is_relative_to(RUNS_DIR.resolve()):
            self._send_error_json("Path traversal detected", 400)
            return
        script_path = param_scripts.stage_run_folder(prepared, work_dir)
        vis_meta = {
            "system": prepared["meta"]["title"],
            "types": {"1": {"name": "disc", "color": "#38bdf8", "radius": 1.1}},
            "box_size": [48.35, 48.35, 0.2],
        }
        exec_start = runner.run_script(script_path=script_path, run_id=run_id, visual_metadata=vis_meta,
                                       conversation_id="param-runs", sync=False)
        if not exec_start.get("success", False):
            self._send_error_json(exec_start.get("error", "Execution failed to initialize"), 400)
            return
        self._send_json({"run_id": run_id, "status": "running", "changed_lines": prepared["changed_lines"],
                         "viewer": prepared["viewer"],
                         "message": "Simulation started. Stream output via /api/run/stream."})

    def _handle_run_stream(self, qs: dict):
        """Native Server-Sent Events stream for live terminal log and trajectory frames.
        
        Per browser specification, EventSource cannot set custom headers, so authentication
        token is passed and verified via query string: ?token=...
        """
        token = qs.get("token", [None])[0]
        if not secrets.compare_digest(str(token or ""), SESSION_TOKEN):
            self._send_error_json("Forbidden: Invalid or missing token query parameter", 403)
            return

        run_id = qs.get("run_id", [None])[0]
        if not run_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
            self._send_error_json("Invalid or missing run_id parameter", 400)
            return

        # Start SSE response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._set_cors_headers()
        self.end_headers()

        def send_sse(event: str, payload: dict):
            msg = f"event: {event}\ndata: {json.dumps(payload)}\n\n"
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()

        # Wait briefly for run state to register if needed
        state = None
        for _ in range(20):
            state = get_run_state(run_id)
            if state:
                break
            time.sleep(0.05)

        if not state:
            send_sse("done", {"run_id": run_id, "status": "error", "error": "Run not found."})
            return

        # 1. Handshake Event
        units = state.get("units")
        if not units:
            from app.lammps.ovito_renderer import detect_units
            dump_p = Path(state.get("dump_file", ""))
            units = detect_units(dump_p)
            state["units"] = units

        avail = state.get("available_fields")
        if not avail:
            script_text = state.get("script", "")
            is_synth = state.get("is_synthetic", False)
            has_ke = bool(re.search(r"compute\s+\w+\s+\w+\s+ke/atom", script_text, re.IGNORECASE) or "c_atomke" in script_text.lower() or is_synth)
            has_stress = bool(re.search(r"compute\s+\w+\s+\w+\s+stress/atom", script_text, re.IGNORECASE) or "v_vonmises" in script_text.lower())
            avail = ["element"]
            if has_ke:
                avail.append("kinetic_energy")
            if has_stress:
                avail.append("von_mises_stress")
            state["available_fields"] = avail

        send_sse("handshake", {
            "run_id": run_id,
            "engine": state["engine"],
            "is_synthetic": state["is_synthetic"],
            "units": units,
            "available_fields": avail,
            "visual_metadata": state.get("visual_metadata", {})
        })

        # 2. Streaming Loop
        log_idx = 0
        frame_idx = 0

        try:
            while True:
                state = get_run_state(run_id)
                if not state:
                    break

                # Emit new console log lines
                stdout_lines = state.get("stdout_lines", [])
                if log_idx < len(stdout_lines):
                    for line in stdout_lines[log_idx:]:
                        send_sse("log", {"line": line})
                    log_idx = len(stdout_lines)

                # Emit new trajectory frames
                frames = state.get("frames", [])
                if frame_idx < len(frames):
                    for fr in frames[frame_idx:]:
                        send_sse("frame", fr)
                    frame_idx = len(frames)

                # Terminal status check
                status = state.get("status")
                if status in ("completed", "error", "timeout"):
                    # Flush any final lines or frames
                    stdout_lines = state.get("stdout_lines", [])
                    if log_idx < len(stdout_lines):
                        for line in stdout_lines[log_idx:]:
                            send_sse("log", {"line": line})
                    frames = state.get("frames", [])
                    if frame_idx < len(frames):
                        for fr in frames[frame_idx:]:
                            send_sse("frame", fr)

                    render_res = state.get("render_result") or {}
                    render_avail = bool(render_res.get("available"))

                    send_sse("done", {
                        "run_id": run_id,
                        "status": status,
                        "engine": state.get("engine"),
                        "is_synthetic": state.get("is_synthetic", False),
                        "runtime_seconds": state.get("runtime_seconds", 0.0),
                        "error": state.get("error"),
                        "thermo": state.get("thermo"),
                        "render_available": render_avail,
                        "coordination_histogram": render_res.get("coordination_histogram"),
                        "coordination_cutoff": render_res.get("coordination_cutoff"),
                        "cutoff_source": render_res.get("cutoff_source"),
                        "units": render_res.get("units") or state.get("units"),
                        "render_result": render_res,
                        "render_url": f"/api/run/render?run_id={run_id}" if render_avail else None
                    })
                    break

                time.sleep(0.04)

        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_run_render(self, qs: dict):
        """Serves post-run rendered OVITO PNG."""
        run_id = qs.get("run_id", [None])[0]
        if not run_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
            self._send_error_json("Invalid or missing run_id", 400)
            return

        runs_dir_resolved = RUNS_DIR.resolve()
        render_path = (RUNS_DIR / run_id / "render.png").resolve()

        if not render_path.is_relative_to(runs_dir_resolved) or not render_path.exists() or not render_path.is_file():
            self._send_error_json("Rendered image not found", 404)
            return

        try:
            img_bytes = render_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self._set_cors_headers()
            self.send_header("Content-Length", str(len(img_bytes)))
            self.end_headers()
            self.wfile.write(img_bytes)
        except Exception as e:
            self._send_error_json(f"Error reading image: {str(e)}", 500)

    def _serve_static(self, path: str):
        """Serves static assets with CSRF session token injection in index.html."""
        clean_path = path.lstrip("/")
        if not clean_path or clean_path == "index.html":
            index_path = STATIC_DIR / "index.html"
            if not index_path.exists():
                self._send_error_json("index.html not found", 404)
                return
            content = index_path.read_text(encoding="utf-8")
            injection = f'<script>window.__SESSION_TOKEN__ = "{SESSION_TOKEN}";</script>\n</head>'
            content = content.replace("</head>", injection, 1)
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._set_cors_headers()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        target_file = (STATIC_DIR / clean_path).resolve()
        static_dir_resolved = STATIC_DIR.resolve()

        if not target_file.is_relative_to(static_dir_resolved) or not target_file.exists() or not target_file.is_file():
            self._send_error_json("File not found", 404)
            return

        ext = target_file.suffix.lower()
        content_type = MIME_TYPES.get(ext, "application/octet-stream")

        try:
            content_bytes = target_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self._set_cors_headers()
            self.send_header("Content-Length", str(len(content_bytes)))
            self.end_headers()
            self.wfile.write(content_bytes)
        except Exception as e:
            self._send_error_json(f"Error reading file: {str(e)}", 500)


def update_env_file(env_path: Path, updates: Dict[str, str]) -> None:
    """Set KEY=VALUE pairs in a .env file, keeping every other line intact."""
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(updates)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in remaining.items())
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def start_server(host: str = HOST, port: int = PORT):
    """Starts the zero-dependency Python standard library HTTP server."""
    detection = detect_lammps()
    print("=" * 65)
    print("  LAMMPS Research Assistant — Standard Library Server")
    print(f"  Local URL: http://{host}:{port}")
    print(f"  CSRF Protection: Active (session token initialized)")
    print(f"  Status: {detection['status_text']}")
    print(f"  Workspace RAG: READY ({len(router.retriever.chunks)} docs indexed)")
    print("=" * 65)

    server = ThreadingHTTPServer((host, port), LAMMPSRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()
