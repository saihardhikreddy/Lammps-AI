"""Regression tests for the issues found in the 30 Sep 2026 review.

Each test pins down a specific defect so it cannot silently return. The final class runs the
generated scripts in a real LAMMPS binary when one is installed (skipped otherwise).
"""
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from app.generation.intent import IntentExtractor
from app.generation.generator import ScriptGenerator
from app.generation.templates import (
    template_lj_fluid, template_water_liquid, template_molten_metal, gk_window,
)
from app.knowledge.retriever import LocalKnowledgeRetriever
from app.lammps.validator import ScriptValidator, is_escaping_path
from app.lammps.detector import parse_installed_packages


def production_fix(script: str) -> str:
    """Style of the production integrator (the 'prod' fix)."""
    m = re.search(r"^fix\s+prod\s+all\s+(\S+)", script, re.MULTILINE)
    return m.group(1) if m else ""


class TestGeneratorScience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor = IntentExtractor()
        cls.generator = ScriptGenerator(LocalKnowledgeRetriever())
        cls.validator = ScriptValidator()

    def gen(self, text):
        return self.generator.generate(self.extractor.extract_intent(text))

    # Water must be real SPC/E molecules, not a box of uncharged oxygen atoms
    def test_water_script_builds_charged_rigid_molecules(self):
        script = self.gen("Generate a liquid water simulation at 300 K")["script"]
        self.assertIn("molecule        h2o spce.mol", script)
        self.assertRegex(script, r"create_atoms\s+0 box mol h2o")
        self.assertIn('print           "1   -0.8476"', script)
        self.assertIn('print           "2    0.4238"', script)
        self.assertIn("fix             rigidH2O all shake", script)
        # SHAKE must be switched on after minimization (older LAMMPS cannot minimize with it)
        self.assertLess(script.index("minimize"), script.index("fix             rigidH2O"))
        self.assertTrue(self.validator.validate_static(script)["valid"])

    def test_validator_rejects_uncharged_kspace_and_bondless_shake(self):
        broken_water = (
            "units real\natom_style full\nboundary p p p\nlattice fcc 3.9\n"
            "region b block 0 5 0 5 0 5\ncreate_box 2 b bond/types 1 angle/types 1\n"
            "create_atoms 1 box\nmass 1 15.9994\nmass 2 1.008\n"
            "pair_style lj/cut/coul/long 9.8\npair_coeff * * 0.1553 3.166\nkspace_style pppm 1e-4\n"
            "fix s all shake 0.0001 20 0 b 1 a 1\nvelocity all create 300 1\n"
            "fix 1 all nvt temp 300 300 100\ntimestep 1\nrun 100\n"
        )
        errors = " ".join(self.validator.validate_static(broken_water)["errors"])
        self.assertIn("no atom charges", errors)
        self.assertIn("no bonds exist", errors)

    # Transport properties default to NVE production; the plan must agree with the script
    def test_diffusion_defaults_to_nve_and_plan_matches(self):
        res = self.gen("Calculate the diffusion coefficient of liquid argon at 85 K")
        self.assertEqual(production_fix(res["script"]), "nve")
        self.assertEqual(res["production_ensemble"], "NVE")
        prod_stage = [s for s in res["plan"]["stages"] if s.startswith("Production")][0]
        self.assertIn("NVE", prod_stage)
        self.assertIn("v_D_fit", res["script"])

    def test_viscosity_defaults_to_nve(self):
        res = self.gen("Calculate shear viscosity using Green-Kubo for Lennard-Jones liquid")
        self.assertEqual(production_fix(res["script"]), "nve")

    def test_explicit_thermostat_for_transport_is_honored_but_flagged(self):
        res = self.gen("Diffusion coefficient of water at 300 K in NVT")
        self.assertEqual(production_fix(res["script"]), "nvt")
        self.assertTrue(any("Transport WARNING" in a for a in res["assumptions"]))
        warnings = " ".join(self.validator.validate_static(res["script"])["warnings"])
        self.assertIn("thermostat", warnings)

    def test_every_supported_ensemble_reaches_production(self):
        for ens, style in [("NVE", "nve"), ("NVT", "nvt"), ("NPT", "npt"), ("Langevin", "nve")]:
            for system in ["water at 300 K", "molten copper at 1500 K", "Lennard-Jones liquid"]:
                script = self.gen(f"Simulate {system} in {ens}")["script"]
                self.assertEqual(production_fix(script), style, f"{system} {ens}")
                if ens == "Langevin":
                    self.assertIn("fix             prodLgv all langevin", script)

    def test_calculate_requests_generate_scripts_but_questions_do_not(self):
        self.assertEqual(self.extractor.extract_intent(
            "Calculate the diffusion coefficient of liquid argon at 85 K")["intent"], "GENERATE_SCRIPT")
        self.assertEqual(self.extractor.extract_intent(
            "Compute the RDF of molten copper at 1500 K")["intent"], "GENERATE_SCRIPT")
        self.assertNotEqual(self.extractor.extract_intent(
            "How do I calculate the diffusion coefficient of water?")["intent"], "GENERATE_SCRIPT")

    def test_without_thermostat_is_not_read_as_nvt_request(self):
        spec = self.extractor.extract_intent("Simulate LJ liquid diffusion without a thermostat")
        self.assertFalse(spec["ensemble_specified"])

    # Nickel's DYNAMO funcfl file needs pair_style eam, not eam/alloy
    def test_nickel_uses_funcfl_pair_style(self):
        script = self.gen("Simulate molten nickel at 1900 K")["script"]
        self.assertIn("pair_style      eam\n", script)
        self.assertIn("pair_coeff      1 1 Ni_u3.eam", script)
        self.assertNotIn("eam/alloy", script)

    def test_metal_melt_protocol_superheats(self):
        res = self.gen("Simulate molten aluminum at 1000 K")
        m = re.search(r"fix\s+melt all npt temp 300\.0 (\S+)", res["script"])
        self.assertIsNotNone(m)
        self.assertGreaterEqual(float(m.group(1)), 1.5 * 933.47 - 1)

    def test_below_melting_request_reports_the_temperature_actually_used(self):
        res = self.gen("Simulate molten copper at 1000 K")
        self.assertTrue(any("instead of the requested 1000.0 K" in a for a in res["assumptions"]))
        self.assertIn("prod all nvt temp 1457.77 1457.77", res["script"])

    # Green-Kubo: window long enough, result printed by LAMMPS, thermo compatible with Nfreq
    def test_green_kubo_window_and_output(self):
        script = template_water_liquid(compute_viscosity=True, ensemble="NVE")
        s, p = gk_window("real")
        self.assertGreaterEqual(s * p, 1000)
        self.assertIn(f"ave/correlate {s} {p} {s * p}", script)
        self.assertIn("v_eta", script)
        thermo = int(re.findall(r"^thermo\s+(\d+)", script, re.MULTILINE)[-1])
        self.assertEqual(thermo % (s * p), 0)

    # Stated parameters are threaded through (or their override is reported)
    def test_timestep_units_are_converted(self):
        self.assertIn("timestep        0.002", self.gen("Simulate molten copper at 1500 K, timestep 2 fs")["script"])
        self.assertIn("timestep        0.5", self.gen("Simulate water at 300 K with timestep 0.5 fs")["script"])
        self.assertIn("timestep        0.5", self.gen("Simulate water at 300 K with timestep 0.0005 ps")["script"])

    def test_atom_count_and_intervals_are_threaded(self):
        res = self.gen("Simulate molten copper at 1500 K with 4000 atoms, dump every 250, thermo 200")
        self.assertIn("region          box block 0 10 0 10 0 10", res["script"])
        self.assertIn("dump            traj all custom 250", res["script"])
        self.assertRegex(res["script"], r"(?m)^thermo\s+200")
        self.assertTrue(any("generated 4000" in a for a in res["assumptions"]))

    def test_quench_request_is_not_silently_replaced(self):
        res = self.gen("Cool liquid aluminum from 1200 K to 900 K with cooling rate 0.5 K/ps")
        self.assertTrue(any("Quench/cooling protocols are not implemented" in a for a in res["assumptions"]))

    def test_no_von_mises_in_liquid_templates(self):
        for script in (template_lj_fluid(), template_water_liquid(), template_molten_metal()):
            self.assertNotIn("vonMises", script)
            self.assertNotIn("stress/atom", script)


class TestValidatorAndSandbox(unittest.TestCase):
    def test_escaping_paths(self):
        for bad in ["/etc/passwd", "~/x", "../a", "a/../../b", "C:\\x", "\\\\server\\share"]:
            self.assertTrue(is_escaping_path(bad), bad)
        for ok in ["/", "spce.mol", "v_a", "...", "Cu_zhou.eam.alloy", "dump.lammpstrj"]:
            self.assertFalse(is_escaping_path(ok), ok)

    def test_validator_flags_outside_paths(self):
        v = ScriptValidator().validate_static(
            "units lj\nregion b block 0 1 0 1 0 1\ncreate_box 1 b\ncreate_atoms 1 box\n"
            "write_data /tmp/x.data\nrun 1\n")
        self.assertFalse(v["valid"])

    def test_validator_no_false_positive_on_division(self):
        v = ScriptValidator().validate_static(
            "units lj\nregion b block 0 1 0 1 0 1\ncreate_box 1 b\ncreate_atoms 1 box\n"
            "variable r equal v_a / v_b\nrun 1\n")
        self.assertTrue(v["valid"], v["errors"])


class TestDetector(unittest.TestCase):
    def test_parse_installed_packages_spans_lines(self):
        help_text = (
            "Large-scale Atomic/Molecular Massively Parallel Simulator - 22 Jul 2025\n\n"
            "Installed packages:\n\n"
            "ASPHERE BODY CLASS2 EXTRA-PAIR\n"
            "KSPACE MANYBODY MOLECULE RIGID\n\n"
            "List of individual style options included in this LAMMPS executable\n"
        )
        pkgs = parse_installed_packages(help_text)
        self.assertEqual(pkgs, ["ASPHERE", "BODY", "CLASS2", "EXTRA-PAIR", "KSPACE", "MANYBODY", "MOLECULE", "RIGID"])


class TestRunnerSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_runner_blocks_file_writes_outside_run_folder(self):
        from app.lammps.runner import SimulationRunner
        script = self.tmp / "x.in"
        script.write_text("units lj\nprint \"x\" file ../../escape.txt\n", encoding="utf-8")
        res = SimulationRunner(executable_path="builtin").run_script(script, "test_escape_block", sync=True)
        self.assertFalse(res["success"])
        self.assertIn("outside the run folder", res["error"])

    def test_timeout_kills_a_hung_process(self):
        import app.lammps.runner as runner_mod
        fake = self.tmp / "fake_lmp"
        fake.write_text("#!/bin/sh\necho started\nsleep 60\n", encoding="utf-8")
        fake.chmod(0o755)
        script = self.tmp / "x.in"
        script.write_text("units lj\nrun 10\n", encoding="utf-8")
        original = runner_mod.EXECUTION_TIMEOUT_SECONDS
        runner_mod.EXECUTION_TIMEOUT_SECONDS = 2
        try:
            r = runner_mod.SimulationRunner(executable_path=str(fake))
            r._get_executable = lambda: str(fake)
            t0 = time.time()
            res = r.run_script(script, "test_timeout_watchdog", sync=True)
            self.assertLess(time.time() - t0, 20)
            self.assertEqual(res["status"], "timeout")
        finally:
            runner_mod.EXECUTION_TIMEOUT_SECONDS = original

    def test_old_runs_are_evicted(self):
        import app.lammps.runner as runner_mod
        with runner_mod._run_states_lock:
            for k in range(runner_mod.MAX_RETAINED_RUNS + 10):
                runner_mod._run_states[f"evict_{k}"] = {"status": "completed", "start_time": k, "frames": [1] * 10}
            runner_mod._evict_old_runs_locked()
            self.assertLessEqual(len(runner_mod._run_states), runner_mod.MAX_RETAINED_RUNS)
            for k in list(runner_mod._run_states):
                if k.startswith("evict_"):
                    runner_mod._run_states.pop(k)

    def test_synthetic_log_is_labelled_and_not_disguised_as_lammps(self):
        from app.lammps.runner import SimulationRunner, get_run_state
        script = self.tmp / "x.in"
        script.write_text(template_lj_fluid(nsteps=200, eq_steps=100), encoding="utf-8")
        res = SimulationRunner(executable_path="builtin").run_script(script, "test_synth_label", sync=True)
        self.assertTrue(res["is_synthetic"])
        log_text = Path(res["log_file"]).read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC DATA", log_text.splitlines()[0])
        self.assertNotIn("LAMMPS (", log_text)
        self.assertNotIn("Performance:", log_text)


class TestEnvHandling(unittest.TestCase):
    def test_update_env_file_preserves_other_settings(self):
        from app.ui.server import update_env_file
        d = Path(tempfile.mkdtemp())
        env = d / ".env"
        env.write_text("# comment\nLAMMPS_ASSISTANT_PORT=9000\nGEMINI_API_KEY=old\n", encoding="utf-8")
        update_env_file(env, {"GEMINI_API_KEY": "new", "GEMINI_MODEL": "m"})
        text = env.read_text(encoding="utf-8")
        self.assertIn("# comment", text)
        self.assertIn("LAMMPS_ASSISTANT_PORT=9000", text)
        self.assertIn("GEMINI_API_KEY=new", text)
        self.assertIn("GEMINI_MODEL=m", text)
        self.assertNotIn("old", text)
        shutil.rmtree(d)

    def test_core_has_no_pydantic_dependency(self):
        root = Path(__file__).resolve().parent.parent / "app"
        for py in root.rglob("*.py"):
            self.assertNotRegex(py.read_text(encoding="utf-8"), r"^\s*(from|import)\s+pydantic",
                                f"{py} imports pydantic")


class TestSecretExposure(unittest.TestCase):
    def test_workspace_reader_refuses_dotfiles_and_secrets(self):
        from app.knowledge.workspace_indexer import WorkspaceProjectIndexer
        d = Path(tempfile.mkdtemp())
        (d / ".env").write_text("GEMINI_API_KEY=secret\n", encoding="utf-8")
        (d / "server.key").write_text("x", encoding="utf-8")
        (d / "in.melt").write_text("units lj\n", encoding="utf-8")
        idx = WorkspaceProjectIndexer()
        idx.open_workspace(str(d))
        self.assertIsNone(idx.read_workspace_file(".env"))
        self.assertIsNone(idx.read_workspace_file("server.key"))
        self.assertIsNone(idx.read_workspace_file("../etc/passwd"))
        self.assertEqual(idx.read_workspace_file("in.melt"), "units lj\n")
        shutil.rmtree(d)

    def test_public_vercel_handler_disables_workspace_endpoints(self):
        import json
        import threading
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from api.index import handler
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_port}"
        try:
            for path, body in [("/api/project/open", {"folder_path": "/"}), ("/api/project/read", {"rel_path": ".env"})]:
                req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                             headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req, timeout=5)
                self.assertEqual(ctx.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(base + "/api/project/tree", timeout=5)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_env_is_never_shipped(self):
        root = Path(__file__).resolve().parent.parent
        for ignore_file in (".gitignore", ".vercelignore"):
            lines = [l.strip() for l in (root / ignore_file).read_text(encoding="utf-8").splitlines()]
            self.assertIn(".env", lines, ignore_file)


def _find_lmp():
    return shutil.which("lmp") or shutil.which("lmp_serial") or shutil.which("lmp_mpi")


@unittest.skipUnless(_find_lmp(), "LAMMPS binary not installed; real-execution checks skipped")
class TestTemplatesRunInRealLAMMPS(unittest.TestCase):
    """Runs shortened versions of every template in LAMMPS and checks the physics."""

    def run_lammps(self, script: str):
        d = Path(tempfile.mkdtemp())
        (d / "in.run").write_text(script, encoding="utf-8")
        proc = subprocess.run([_find_lmp(), "-in", "in.run", "-screen", "none", "-log", "log.lammps"],
                              cwd=d, capture_output=True, text=True, timeout=600)
        log = (d / "log.lammps").read_text(encoding="utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, [l for l in log.splitlines() if "ERROR" in l])
        self.assertNotIn("ERROR", log)
        return d, log

    @staticmethod
    def last_thermo(log: str):
        blocks = re.split(r"\n\s*Step", log)
        header = ("Step" + blocks[-1].splitlines()[0]).split()
        rows = [l.split() for l in blocks[-1].split("Loop time")[0].splitlines()[1:] if l.strip()]
        return dict(zip(header, map(float, rows[-1])))

    def test_spce_water_energy_matches_literature(self):
        d, log = self.run_lammps(template_water_liquid(nsteps=500, eq_steps=1000))
        last = self.last_thermo(log)
        pe_per_molecule = last["PotEng"] / 216
        # SPC/E configurational energy is about -11.2 kcal/mol at 300 K
        self.assertTrue(-12.5 < pe_per_molecule < -10.0, pe_per_molecule)
        self.assertTrue(0.9 < last["Density"] < 1.1, last["Density"])
        shutil.rmtree(d)

    def test_aluminum_actually_melts(self):
        d, log = self.run_lammps(template_molten_metal(
            nsteps=1000, eq_steps=1000, t_stop=1100, t_melt=933.47, compute_msd=True, ensemble="NVE"))
        msd = [float(l.split()[1]) for l in (d / "molten_msd.out").read_text().splitlines()
               if l.strip() and not l.startswith("#")]
        # A solid's MSD plateaus below ~0.5 A^2; a liquid's keeps growing
        self.assertGreater(msd[-1], 2.0)
        self.assertGreater(msd[-1], 1.5 * msd[len(msd) // 2])
        shutil.rmtree(d)

    def test_lj_npt_and_green_kubo_run(self):
        d, log = self.run_lammps(template_lj_fluid(nsteps=2000, eq_steps=1000, ensemble="NPT", compute_viscosity=True))
        self.assertIn("v_eta", log)
        shutil.rmtree(d)

    def test_nickel_and_iron_potentials_load(self):
        pots = os.environ.get("LAMMPS_POTENTIALS", "")
        if not pots or not Path(pots, "Ni_u3.eam").exists():
            self.skipTest("LAMMPS_POTENTIALS with Ni_u3.eam not available")
        for kwargs in [
            dict(material="Nickel", element="Ni", lattice_a=3.52, mass=58.69, pot_file="Ni_u3.eam",
                 pair_style="eam", t_stop=1900, t_melt=1728),
            dict(material="Iron", element="Fe", lattice_a=2.8665, mass=55.845, pot_file="Fe_mm.eam.fs",
                 pair_style="eam/fs", lattice_style="bcc", t_stop=2000, t_melt=1811, n_cells=6),
        ]:
            d, _ = self.run_lammps(template_molten_metal(nsteps=200, eq_steps=200, **kwargs))
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
