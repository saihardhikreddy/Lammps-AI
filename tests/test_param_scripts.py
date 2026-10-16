"""Parameter Runs tab: variable detection, rendering, validation, endpoints, real run."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from app.lammps import param_scripts as ps
from app.lammps.detector import detect_lammps
from app.ui.server import LAMMPSRequestHandler, SESSION_TOKEN


def _source():
    return ps._entry("active-liquid")[2]


class TestDetection(unittest.TestCase):
    def test_detects_only_literal_variables_before_first_run(self):
        names = [v["name"] for v in ps.detect_variables(_source())]
        self.assertEqual(names, ["input", "damp", "a_force", "relax_steps", "prod_steps", "dump_every",
                                 "dumpfile", "output"])
        # formulas such as next(nf), logfreq(...) and -c_myVirial[1] are not parameters

    def test_types_styles_labels_and_locks(self):
        v = {x["name"]: x for x in ps.detect_variables(_source())}
        self.assertEqual((v["damp"]["style"], v["damp"]["type"], v["damp"]["default"]), ("equal", "float", "1.0"))
        self.assertEqual((v["relax_steps"]["type"], v["relax_steps"]["default"]), ("int", "50000"))
        self.assertEqual((v["input"]["style"], v["input"]["type"]), ("string", "string"))
        self.assertIn("Langevin damping", v["damp"]["label"])
        self.assertFalse(v["dumpfile"]["editable"])
        self.assertTrue(v["a_force"]["editable"])

    def test_after_run_and_continuation_ignored(self):
        text = "variable a equal 1\nvariable b equal &\n 2\nvariable c string x # note\nrun 10\nvariable d equal 4\n"
        self.assertEqual([v["name"] for v in ps.detect_variables(text)], ["a", "c"])

    def test_viewer_dump_report(self):
        self.assertTrue(ps.find_viewer_dump(_source())["ok"])
        self.assertIn("no z", ps.find_viewer_dump(_source())["message"])
        self.assertFalse(ps.find_viewer_dump("dump d all custom 10 f id vx\nrun 1\n")["ok"])
        self.assertIsNone(ps.find_viewer_dump("dump d all custom 10 f id type x y z\n")["message"])


class TestRendering(unittest.TestCase):
    def test_only_target_lines_change_and_style_is_kept(self):
        src = _source()
        out = ps.prepare("active-liquid", {"a_force": 2.5, "relax_steps": "1000"})
        before, after = src.split("\n"), out["text"].split("\n")
        self.assertEqual(len(before), len(after))
        diff = [i + 1 for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(diff, out["changed_lines"])
        self.assertEqual(len(diff), 2)
        self.assertTrue(after[diff[0] - 1].startswith("variable        a_force     equal  2.5      #"))
        self.assertTrue(after[diff[1] - 1].startswith("variable        relax_steps equal  1000    #"))

    def test_unchanged_values_render_identically(self):
        out = ps.prepare("active-liquid", {"damp": "1", "relax_steps": 50000.0})
        self.assertEqual(out["text"], _source())
        self.assertEqual(out["changed_lines"], [])

    def test_bad_values_rejected(self):
        bad = {"damp": [float("nan"), "nan", "inf", "1e999", "300\nshell ls", "1 # x", True, None, [1], "abc"],
               "relax_steps": [1.5, "10 20"], "nope": [1], "input": ["../x", "/etc/passwd", "a b", "x;rm"],
               "dumpfile": ["other.lammpstrj"]}
        for name, values in bad.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ps.ParamError) as cm:
                        ps.prepare("active-liquid", {name: value})
                    self.assertIn(name, cm.exception.errors)

    def test_unknown_script(self):
        with self.assertRaises(KeyError):
            ps.prepare("../etc", {})

    def test_original_file_untouched(self):
        path = ps.PARAM_SCRIPTS_DIR / "active-liquid" / "in.activeliquid"
        before = path.read_bytes()
        ps.prepare("active-liquid", {"a_force": 3})
        self.assertEqual(path.read_bytes(), before)


class TestEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LAMMPSRequestHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _req(self, path, data=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Session-Token"] = SESSION_TOKEN
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_list_requires_token(self):
        self.assertEqual(self._req("/api/param-scripts", token=False)[0], 403)
        status, data = self._req("/api/param-scripts")
        self.assertEqual(status, 200)
        self.assertEqual([s["id"] for s in data["scripts"]], ["active-liquid"])
        self.assertEqual(len(data["scripts"][0]["variables"]), 8)

    def test_run_requires_token_and_validates(self):
        self.assertEqual(self._req("/api/param-scripts/run", {"file_id": "active-liquid"}, token=False)[0], 403)
        status, data = self._req("/api/param-scripts/run", {"file_id": "active-liquid", "params": {"damp": "300\nshell ls"}})
        self.assertEqual(status, 400)
        self.assertIn("damp", data["fields"])
        self.assertEqual(self._req("/api/param-scripts/run", {"file_id": "nope", "params": {}})[0], 404)

    def test_dry_run_returns_edited_script(self):
        status, data = self._req("/api/param-scripts/run",
                                 {"file_id": "active-liquid", "params": {"a_force": 4}, "dry_run": True})
        self.assertEqual(status, 200)
        self.assertEqual(len(data["changed_lines"]), 1)
        self.assertIn("a_force     equal  4 ", data["script"])

    @unittest.skipUnless(detect_lammps().get("detected"), "no LAMMPS binary")
    def test_real_run_streams_frames(self):
        status, data = self._req("/api/param-scripts/run", {
            "file_id": "active-liquid",
            "params": {"a_force": 2.0, "relax_steps": 2000, "prod_steps": 4000, "dump_every": 200}})
        self.assertEqual(status, 200, data)
        url = f"{self.base}/api/run/stream?run_id={data['run_id']}&token={SESSION_TOKEN}"
        frames, done, event = 0, None, None
        with urllib.request.urlopen(url, timeout=180) as r:
            for raw in r:
                line = raw.decode().rstrip("\n")
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    if event == "frame":
                        frames += 1
                    elif event == "done":
                        done = json.loads(line[6:])
                        break
        self.assertEqual(done["status"], "completed", done.get("error"))
        self.assertFalse(done["is_synthetic"])
        self.assertGreaterEqual(frames, 20)


if __name__ == "__main__":
    unittest.main()
