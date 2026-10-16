"""Integration Tests for the Standard Library HTTP Server and SSE Streaming."""
import unittest
import threading
import time
import json
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock

from app.ui.server import LAMMPSRequestHandler, router, SESSION_TOKEN


class TestStdlibServer(unittest.TestCase):
    """Tests the zero-dependency Python standard library HTTP server."""

    @classmethod
    def setUpClass(cls):
        # Start server on an ephemeral free port (port 0)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LAMMPSRequestHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        # Mock LLMs to offline mode for fast, deterministic unit testing
        router.gemini_client.is_available = lambda: False
        router.local_llm.is_available = lambda: False

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _http_get(self, path: str, headers: dict = None):
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8"), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), e.headers

    def _http_post(self, path: str, data: dict, headers: dict = None):
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode("utf-8")
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8"), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), e.headers

    def test_serve_index_html(self):
        """Verify GET / returns 200 and injects window.__SESSION_TOKEN__."""
        status, body, _ = self._http_get("/")
        self.assertEqual(status, 200)
        self.assertIn("window.__SESSION_TOKEN__", body)
        self.assertIn(SESSION_TOKEN, body)
        self.assertIn("<!DOCTYPE html>", body)

    def test_status_endpoint(self):
        """Verify GET /api/status returns standard library framework and status metrics."""
        status, body, _ = self._http_get("/api/status")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("ThreadingHTTPServer", data["framework"])
        self.assertIn("lammps", data)
        self.assertIn("status_text", data)

    def test_chat_endpoint_generates_script(self):
        """Verify POST /api/chat dispatches message through router and generates script."""
        payload = {
            "conversation_id": "test_conv_stdlib",
            "message": "Simulate molten aluminum at 1000 K"
        }
        status, body, _ = self._http_post("/api/chat", payload, headers={"X-Session-Token": SESSION_TOKEN})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["intent"], "GENERATE_SCRIPT")
        self.assertIsNotNone(data["script"])
        self.assertTrue(data["validation"]["valid"])

    def test_run_endpoint_rejects_without_session_token(self):
        """Verify POST /api/run rejects unauthorized requests missing the session token."""
        payload = {
            "script": "units metal\nrun 10\n"
        }
        status, body, _ = self._http_post("/api/run", payload)
        self.assertEqual(status, 403)

    def test_run_and_stream_sse_lifecycle(self):
        """Verify POST /api/run starts async run and GET /api/run/stream streams SSE events."""
        script_code = (
            "units lj\n"
            "atom_style atomic\n"
            "boundary p p p\n"
            "lattice fcc 0.8442\n"
            "region box block 0 2 0 2 0 2\n"
            "create_box 1 box\n"
            "create_atoms 1 box\n"
            "mass 1 1.0\n"
            "velocity all create 1.44 12345\n"
            "pair_style lj/cut 2.5\n"
            "pair_coeff 1 1 1.0 1.0 2.5\n"
            "fix 1 all nvt temp 1.44 1.44 0.5\n"
            "thermo 20\n"
            "dump traj all custom 20 dump.lammpstrj id type x y z\n"
            "run 40\n"
        )
        payload = {
            "script": script_code,
            "session_token": SESSION_TOKEN
        }
        status, body, _ = self._http_post("/api/run", payload)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "running")
        self.assertIn("run_id", data)

        run_id = data["run_id"]

        # Stream SSE events via GET /api/run/stream?run_id=...&token=...
        stream_url = f"{self.base_url}/api/run/stream?run_id={run_id}&token={SESSION_TOKEN}"
        req = urllib.request.Request(stream_url)

        events_received = []
        with urllib.request.urlopen(req, timeout=10) as stream_resp:
            self.assertEqual(stream_resp.status, 200)
            self.assertIn("text/event-stream", stream_resp.headers.get("Content-Type", ""))

            current_event = None
            start_wait = time.time()
            while time.time() - start_wait < 8.0:
                line = stream_resp.readline().decode("utf-8")
                if not line:
                    break
                line_str = line.strip()
                if line_str.startswith("event:"):
                    current_event = line_str.split(":", 1)[1].strip()
                elif line_str.startswith("data:") and current_event:
                    data_str = line_str.split(":", 1)[1].strip()
                    payload = json.loads(data_str)
                    events_received.append((current_event, payload))
                    if current_event == "done":
                        break
                    current_event = None

        event_names = [e[0] for e in events_received]
        self.assertIn("handshake", event_names)
        self.assertIn("log", event_names)
        self.assertIn("frame", event_names)
        self.assertIn("done", event_names)

        # Check handshake payload
        handshake_data = next(d for name, d in events_received if name == "handshake")
        self.assertEqual(handshake_data["run_id"], run_id)
        self.assertIn("engine", handshake_data)

        # Check done payload
        done_data = next(d for name, d in events_received if name == "done")
        self.assertEqual(done_data["status"], "completed")

    def test_stream_endpoint_rejects_invalid_token(self):
        """Verify GET /api/run/stream rejects invalid query tokens."""
        status, body, _ = self._http_get("/api/run/stream?run_id=run_123&token=wrong_token")
        self.assertEqual(status, 403)

    def test_render_endpoint_404_for_missing(self):
        """Verify GET /api/run/render returns 404 when render.png does not exist."""
        status, body, _ = self._http_get("/api/run/render?run_id=nonexistent_run_id")
        self.assertEqual(status, 404)

    def test_api_key_set_endpoint(self):
        """Verify POST /api/key/set sets key and returns 200."""
        # Never touch the developer's real .env during tests
        import tempfile
        from pathlib import Path
        from app import config as app_config
        tmp_env = Path(tempfile.mkdtemp()) / ".env"
        tmp_env.write_text("# settings\nLAMMPS_ASSISTANT_PORT=8000\nGEMINI_API_KEY=old\n", encoding="utf-8")
        original_env = app_config.ENV_FILE
        app_config.ENV_FILE = tmp_env
        try:
            payload = {"api_key": "AIzaSy_dummy_key_1234567890", "model": "gemini-2.5-flash"}
            status, body, _ = self._http_post("/api/key/set", payload, headers={"X-Session-Token": SESSION_TOKEN})
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertTrue(data["success"])
            self.assertTrue(data["gemini_ready"])
            written = tmp_env.read_text(encoding="utf-8")
            # Other settings survive; the key line is replaced, not duplicated
            self.assertIn("LAMMPS_ASSISTANT_PORT=8000", written)
            self.assertIn("# settings", written)
            self.assertIn("GEMINI_API_KEY=AIzaSy_dummy_key_1234567890", written)
            self.assertEqual(written.count("GEMINI_API_KEY="), 1)
        finally:
            app_config.ENV_FILE = original_env
            router.gemini_client.set_api_key("")

    def test_state_changing_posts_require_token(self):
        """Every POST except /api/status must carry the session token."""
        for path, payload in [
            ("/api/chat", {"message": "hello"}),
            ("/api/key/set", {"api_key": "AIzaSy_dummy_key_1234567890"}),
            ("/api/project/open", {"folder_path": "/"}),
            ("/api/project/read", {"rel_path": "README.md"}),
            ("/api/preset", {"preset": "lj_benchmark"}),
        ]:
            status, _, _ = self._http_post(path, payload)
            self.assertEqual(status, 403, path)

    def test_foreign_origin_rejected_and_no_wildcard_cors(self):
        status, _, _ = self._http_post("/api/chat", {"message": "hi"},
                                       headers={"X-Session-Token": SESSION_TOKEN, "Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        status, _, headers = self._http_get("/api/status")
        self.assertEqual(status, 200)
        self.assertNotEqual(headers.get("Access-Control-Allow-Origin"), "*")
        status, _, headers = self._http_get("/api/status", headers={"Origin": self.base_url})
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), self.base_url)

    def test_foreign_host_header_rejected(self):
        """DNS-rebinding defence: a page served from another hostname cannot read local endpoints."""
        status, _, _ = self._http_get("/api/conversations", headers={"Host": f"attacker.example:{self.port}"})
        self.assertEqual(status, 403)

    def test_malformed_body_returns_json_error(self):
        url = f"{self.base_url}/api/chat"
        req = urllib.request.Request(url, data=b"{not json", method="POST",
                                     headers={"Content-Type": "application/json", "X-Session-Token": SESSION_TOKEN})
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("expected HTTP error")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            self.assertIn("error", json.loads(e.read().decode("utf-8")))

    def test_preset_endpoint_returns_validated_template(self):
        status, body, _ = self._http_post("/api/preset", {"preset": "water_liquid"},
                                          headers={"X-Session-Token": SESSION_TOKEN})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["validation"]["valid"], data["validation"])
        self.assertIn("molecule        h2o spce.mol", data["script"])


if __name__ == "__main__":
    unittest.main()
