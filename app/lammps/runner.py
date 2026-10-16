"""Local LAMMPS Execution Engine with Sandboxing, Trajectory Streaming, and Built-in Physics Engine."""
import subprocess
import threading
import time
import os
import shutil
import re
import math
import random
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.config import RUNS_DIR, EXECUTION_TIMEOUT_SECONDS
from app.lammps.detector import detect_lammps
from app.lammps.trajectory_parser import parse_dump_frames, AtomRecord
from app.lammps.ovito_renderer import render_final_frame
from app.lammps.parser import ThermoParser
from app.chatbot.memory import ConversationMemory
from app.lammps.validator import is_escaping_path

SYNTHETIC_ENGINE_NAME = "Local MD Physics Engine (100% Offline)"
MAX_RETAINED_RUNS = 20

# Global registry for active and completed runs
_run_states: Dict[str, Dict[str, Any]] = {}
_run_states_lock = threading.Lock()


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a process and everything it spawned (wsl.exe -> lmp, mpirun -> ranks, shell -> child)."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _evict_old_runs_locked(keep: int = MAX_RETAINED_RUNS) -> None:
    """Drop the oldest finished runs (and their buffered frames) beyond `keep`. Caller holds the lock."""
    finished = [(st.get("start_time", 0.0), rid) for rid, st in _run_states.items()
                if st.get("status") in ("completed", "error", "timeout")]
    excess = len(_run_states) - keep
    for _, rid in sorted(finished)[:max(0, excess)]:
        _run_states.pop(rid, None)


def get_run_state(run_id: str) -> Optional[Dict[str, Any]]:
    """Thread-safe getter for a run state snapshot."""
    with _run_states_lock:
        state = _run_states.get(run_id)
        if state is None:
            return None
        # Return shallow copy with lists copied
        return {
            **state,
            "stdout_lines": list(state.get("stdout_lines", [])),
            "frames": list(state.get("frames", []))
        }


class SimulationRunner:
    """Safely executes LAMMPS simulations locally on configured executables or built-in numerical engine."""

    FORBIDDEN_PATTERNS = [
        r"^\s*shell\b",
        r"^\s*python\b",
        r"^\s*system\b",
        r"^\s*quit\b"
    ]

    def __init__(self, executable_path: Optional[str] = None):
        self.custom_executable = executable_path
        self.thermo_parser = ThermoParser()
        self.memory = ConversationMemory()

    def _get_executable(self) -> Optional[str]:
        if self.custom_executable == "builtin":
            return None
        detection = detect_lammps(self.custom_executable)
        return detection.get("executable")

    def _find_potentials_dir(self, lmp_exe: str) -> Optional[Path]:
        """Finds the installed Potentials directory relative to LAMMPS executable."""
        exe_path = Path(lmp_exe)
        candidates = []
        env_dir = os.environ.get("LAMMPS_POTENTIALS")
        if env_dir:
            candidates.append(Path(env_dir))
        candidates.extend([
            exe_path.parent.parent / "Potentials",          # Windows installer layout
            exe_path.parent / "Potentials",
            exe_path.parent.parent / "share" / "lammps" / "potentials",  # Linux / conda / pip
            exe_path.parent / "share" / "lammps" / "potentials",
            Path("/usr/share/lammps/potentials"),
        ])
        for c in candidates:
            if c.exists() and c.is_dir():
                return c
        return None

    def _auto_link_potentials(self, script_text: str, work_dir: Path, potentials_dir: Optional[Path]):
        """Detects referenced potential files in script and copies them into run directory."""
        if not potentials_dir or not potentials_dir.exists():
            return

        lines = script_text.splitlines()
        for line in lines:
            line = line.split('#')[0].strip()
            if line.startswith("pair_coeff") or line.startswith("pair_style"):
                tokens = line.split()
                for token in tokens:
                    if any(token.endswith(ext) for ext in [".eam", ".alloy", ".fs", ".tersoff", ".sw", ".meam", ".reax", ".table", ".adp", ".bop"]):
                        pot_file = potentials_dir / token
                        if pot_file.exists():
                            target = work_dir / token
                            if not target.exists():
                                try:
                                    shutil.copy2(pot_file, target)
                                except Exception:
                                    pass

    def run_script(
        self,
        script_path: Path,
        run_id: str,
        visual_metadata: Optional[Dict[str, Any]] = None,
        conversation_id: str = "default",
        sync: bool = False
    ) -> Dict[str, Any]:
        """Validates and executes a LAMMPS input script asynchronously or synchronously."""
        # 1. Security validation: run_id regex
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
            return {
                "success": False,
                "error": "Security restriction: Invalid run_id format.",
                "stdout": "",
                "stderr": "Invalid run_id",
                "log_file": None,
                "runtime_seconds": 0.0
            }

        # 2. Security validation: path traversal containment
        runs_dir_resolved = RUNS_DIR.resolve()
        runs_dir_resolved.mkdir(parents=True, exist_ok=True)
        work_dir = (RUNS_DIR / run_id).resolve()
        if not work_dir.is_relative_to(runs_dir_resolved):
            return {
                "success": False,
                "error": "Security restriction: Invalid run_id path traversal.",
                "stdout": "",
                "stderr": "Path traversal detected",
                "log_file": None,
                "runtime_seconds": 0.0
            }

        if not script_path.exists():
            return {
                "success": False,
                "error": f"Script file not found: {script_path}",
                "stdout": "",
                "stderr": "Script input file missing.",
                "log_file": None,
                "runtime_seconds": 0.0
            }

        script_text = script_path.read_text(encoding="utf-8", errors="replace")

        # 3. Security validation: forbidden commands
        clean_lines = [l.split('#')[0].strip() for l in script_text.splitlines()]
        for line in clean_lines:
            if not line:
                continue
            for pat in self.FORBIDDEN_PATTERNS:
                if re.search(pat, line, re.IGNORECASE):
                    return {
                        "success": False,
                        "error": f"Security restriction: Unsafe command pattern '{pat}' detected in script line: '{line}'.",
                        "stdout": "",
                        "stderr": "Security validation blocked execution.",
                        "log_file": None,
                        "runtime_seconds": 0.0
                    }
            # LAMMPS commands such as print/dump/write_data/log can write files; keep them in the run folder
            for tok in line.split()[1:]:
                if is_escaping_path(tok):
                    return {
                        "success": False,
                        "error": f"Security restriction: file path '{tok}' points outside the run folder (line: '{line}').",
                        "stdout": "",
                        "stderr": "Security validation blocked execution.",
                        "log_file": None,
                        "runtime_seconds": 0.0
                    }

        work_dir.mkdir(parents=True, exist_ok=True)

        # Parse units and available fields from script text
        units_m = re.search(r"^\s*units\s+([a-zA-Z0-9_]+)", script_text, re.MULTILINE | re.IGNORECASE)
        units_val = units_m.group(1).lower() if units_m else "metal"

        has_ke = bool(re.search(r"compute\s+\w+\s+\w+\s+ke/atom", script_text, re.IGNORECASE) or "c_atomke" in script_text.lower())
        has_stress = bool(re.search(r"compute\s+\w+\s+\w+\s+stress/atom", script_text, re.IGNORECASE) or "v_vonmises" in script_text.lower())
        avail = ["element"]
        if has_ke:
            avail.append("kinetic_energy")
        if has_stress:
            avail.append("von_mises_stress")

        # Initialize run state in registry
        with _run_states_lock:
            _evict_old_runs_locked()
            _run_states[run_id] = {
                "run_id": run_id,
                "status": "running",
                "engine": "Initializing...",
                "is_synthetic": False,
                "units": units_val,
                "available_fields": avail,
                "script": script_text,
                "work_dir": str(work_dir),
                "script_path": str(script_path),
                "log_file": str(work_dir / "log.lammps"),
                "dump_file": str(work_dir / "dump.lammpstrj"),
                "render_file": str(work_dir / "render.png"),
                "render_result": None,
                "stdout_lines": [],
                "frames": [],
                "last_dump_offset": 0,
                "error": None,
                "returncode": None,
                "runtime_seconds": 0.0,
                "thermo": None,
                "visual_metadata": visual_metadata or {},
                "start_time": time.time(),
                "conversation_id": conversation_id
            }

        worker_thread = threading.Thread(
            target=self._execute_worker,
            args=(script_path, script_text, run_id, work_dir, visual_metadata, conversation_id),
            daemon=True
        )
        worker_thread.start()

        if sync:
            worker_thread.join()
            with _run_states_lock:
                st = _run_states.get(run_id, {})
                return {
                    "success": (st.get("status") == "completed"),
                    "run_id": run_id,
                    "status": st.get("status"),
                    "engine": st.get("engine"),
                    "is_synthetic": st.get("is_synthetic"),
                    "returncode": st.get("returncode", 0),
                    "stdout": "\n".join(st.get("stdout_lines", [])),
                    "stderr": st.get("error") or "",
                    "error": st.get("error"),
                    "log_file": st.get("log_file"),
                    "runtime_seconds": st.get("runtime_seconds", 0.0),
                    "work_dir": str(work_dir),
                    "thermo": st.get("thermo"),
                    "render_result": st.get("render_result")
                }

        return {
            "success": True,
            "run_id": run_id,
            "status": "running",
            "work_dir": str(work_dir)
        }

    def _execute_worker(
        self,
        script_path: Path,
        script_text: str,
        run_id: str,
        work_dir: Path,
        visual_metadata: Optional[Dict[str, Any]],
        conversation_id: str
    ):
        """Worker thread executing the real binary or built-in engine."""
        start_time = time.time()
        log_file = work_dir / "log.lammps"
        dump_file = work_dir / "dump.lammpstrj"
        render_file = work_dir / "render.png"

        units_match = re.search(r"^\s*units\s+([a-zA-Z0-9_]+)", script_text, re.MULTILINE | re.IGNORECASE)
        units = units_match.group(1).lower() if units_match else None

        executable = self._get_executable()

        if executable:
            is_wsl = executable.startswith("wsl:")
            wsl_bin = executable.split(":", 1)[1].replace("\x00", "").strip() if is_wsl else executable
            engine_name = f"WSL2 Ubuntu ({Path(wsl_bin).name})" if is_wsl else f"Local Binary ({Path(executable).name})"

            # Native LAMMPS executable available
            with _run_states_lock:
                if run_id in _run_states:
                    _run_states[run_id]["engine"] = engine_name
                    _run_states[run_id]["is_synthetic"] = False

            work_script = work_dir / "in.run"
            work_script.write_text(script_text.replace("\r\n", "\n"), encoding="utf-8")

            if is_wsl:
                # Ensure the Windows drive is mounted in WSL
                drive_letter = work_dir.resolve().drive.replace(":", "").lower()
                if drive_letter != "c":
                    try:
                        subprocess.run(
                            ["wsl", "-d", "Ubuntu", "-u", "root", "--cd", "~", "bash", "-c", f"mkdir -p /mnt/{drive_letter} && mount -t drvfs {drive_letter.upper()}: /mnt/{drive_letter} 2>/dev/null || true"],
                            capture_output=True,
                            timeout=5
                        )
                    except Exception:
                        pass

                posix_sub = work_dir.resolve().as_posix()
                if ":" in posix_sub:
                    posix_sub = posix_sub.split(":", 1)[1]
                wsl_work_dir = f"/mnt/{drive_letter}{posix_sub}"

                cmd = ["wsl", "-d", "Ubuntu", "--cd", wsl_work_dir, wsl_bin, "-in", "in.run", "-log", "log.lammps"]
                proc_cwd = None
                env = None
            else:
                potentials_dir = self._find_potentials_dir(executable)
                self._auto_link_potentials(script_text, work_dir, potentials_dir)

                env = os.environ.copy()
                if potentials_dir:
                    env["LAMMPS_POTENTIALS"] = str(potentials_dir.resolve())

                cmd = [executable, "-in", "in.run", "-log", "log.lammps"]
                proc_cwd = str(work_dir)

            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=proc_cwd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    # own process group, so a timeout can kill LAMMPS together with any children
                    start_new_session=(os.name != "nt"),
                    creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
                )

                # Watchdog: readline() blocks, so the timeout must be enforced from another thread
                timed_out = threading.Event()

                def _kill_on_timeout():
                    if proc.poll() is None:
                        timed_out.set()
                        _kill_process_tree(proc)

                watchdog = threading.Timer(EXECUTION_TIMEOUT_SECONDS, _kill_on_timeout)
                watchdog.daemon = True
                watchdog.start()

                while True:
                    line = proc.stdout.readline()
                    if not line and proc.poll() is not None:
                        break
                    if line:
                        cleaned = line.rstrip("\r\n")
                        if is_wsl and cleaned.startswith("wsl:"):
                            continue
                        with _run_states_lock:
                            if run_id in _run_states:
                                _run_states[run_id]["stdout_lines"].append(cleaned)

                    # Check for new trajectory frames
                    if dump_file.exists():
                        with _run_states_lock:
                            last_off = _run_states[run_id]["last_dump_offset"] if run_id in _run_states else 0
                        new_frames, new_off = parse_dump_frames(dump_file, last_off)
                        if new_frames:
                            with _run_states_lock:
                                if run_id in _run_states:
                                    _run_states[run_id]["frames"].extend(new_frames)
                                    _run_states[run_id]["last_dump_offset"] = new_off

                # Process finished
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except Exception:
                    pass
                ret_code = proc.wait(timeout=30)
                watchdog.cancel()
                elapsed = time.time() - start_time
                if timed_out.is_set():
                    raise subprocess.TimeoutExpired(cmd, EXECUTION_TIMEOUT_SECONDS)

                # Parse any remaining trajectory frames
                if dump_file.exists():
                    with _run_states_lock:
                        last_off = _run_states[run_id]["last_dump_offset"] if run_id in _run_states else 0
                    new_frames, new_off = parse_dump_frames(dump_file, last_off)
                    if new_frames:
                        with _run_states_lock:
                            if run_id in _run_states:
                                _run_states[run_id]["frames"].extend(new_frames)
                                _run_states[run_id]["last_dump_offset"] = new_off

                # Parse thermo log
                thermo_data = self.thermo_parser.parse_log(log_file) if log_file.exists() else {}

                # OVITO rendering
                render_res = render_final_frame(dump_file, render_file, units=units) if dump_file.exists() else {"available": False, "reason": "No dump file"}

                # Check for errors
                with _run_states_lock:
                    all_stdout = "\n".join(_run_states.get(run_id, {}).get("stdout_lines", []))
                has_error = (ret_code != 0) or ("ERROR:" in all_stdout)
                err_msg = None
                if has_error:
                    for line in all_stdout.splitlines():
                        if "ERROR:" in line:
                            err_msg = line.strip()
                            break
                    if not err_msg:
                        err_msg = f"Process exited with code {ret_code}."

                with _run_states_lock:
                    if run_id in _run_states:
                        _run_states[run_id].update({
                            "status": "error" if has_error else "completed",
                            "returncode": ret_code,
                            "error": err_msg,
                            "runtime_seconds": round(elapsed, 3),
                            "thermo": thermo_data,
                            "render_result": render_res
                        })

                # Save run to SQLite memory
                try:
                    self.memory.save_simulation_run(
                        run_id=run_id,
                        conv_id=conversation_id,
                        script=script_text,
                        ret_code=ret_code,
                        runtime=round(elapsed, 3),
                        summary=thermo_data.get("summary", {}) if isinstance(thermo_data, dict) else {}
                    )
                except Exception:
                    pass

            except subprocess.TimeoutExpired:
                _kill_process_tree(proc)
                with _run_states_lock:
                    if run_id in _run_states:
                        _run_states[run_id].update({
                            "status": "timeout",
                            "returncode": -1,
                            "error": f"Execution timed out (exceeded {EXECUTION_TIMEOUT_SECONDS}s safety limit).",
                            "runtime_seconds": EXECUTION_TIMEOUT_SECONDS
                        })
            except Exception as e:
                with _run_states_lock:
                    if run_id in _run_states:
                        _run_states[run_id].update({
                            "status": "error",
                            "returncode": -1,
                            "error": f"System error during execution: {str(e)}",
                            "runtime_seconds": round(time.time() - start_time, 3)
                        })

        else:
            # Built-in MD Physics Engine (100% Offline fallback)
            self._run_builtin_md_engine(
                run_id=run_id,
                script_text=script_text,
                work_dir=work_dir,
                log_file=log_file,
                dump_file=dump_file,
                render_file=render_file,
                visual_metadata=visual_metadata,
                conversation_id=conversation_id
            )

    def _run_builtin_md_engine(
        self,
        run_id: str,
        script_text: str,
        work_dir: Path,
        log_file: Path,
        dump_file: Path,
        render_file: Path,
        visual_metadata: Optional[Dict[str, Any]],
        conversation_id: str
    ):
        """Simulates an authentic MD trajectory with live streaming of logs and atomic dump frames."""
        start_time = time.time()

        with _run_states_lock:
            if run_id in _run_states:
                _run_states[run_id]["engine"] = SYNTHETIC_ENGINE_NAME
                _run_states[run_id]["is_synthetic"] = True
                _run_states[run_id]["available_fields"] = ["element", "kinetic_energy"]

        # Parse simulation parameters from script
        target_temp = 300.0
        start_temp = 300.0
        n_steps = 1000
        thermo_freq = 50
        dump_freq = 50
        units = "metal"

        for line in script_text.splitlines():
            line = line.split('#')[0].strip()
            if line.startswith("units"):
                parts = line.split()
                if len(parts) > 1:
                    units = parts[1]
            elif "temp" in line and ("nvt" in line or "npt" in line):
                nums = re.findall(r"[-+]?\d*\.\d+|\d+", line)
                if len(nums) >= 2:
                    start_temp = float(nums[0])
                    target_temp = float(nums[1])
            elif line.startswith("thermo "):
                nums = re.findall(r"\d+", line)
                if nums:
                    thermo_freq = max(10, int(nums[0]))
            elif line.startswith("dump ") and "custom" in line:
                tokens = line.split()
                try:
                    c_idx = tokens.index("custom")
                    dump_freq = max(10, int(tokens[c_idx + 1]))
                except (ValueError, IndexError):
                    pass
            elif line.startswith("run "):
                nums = re.findall(r"\d+", line)
                if nums:
                    n_steps = int(nums[0])

        # Emit roughly 100 frames regardless of the requested run length
        step_interval = max(10, n_steps // 100)

        # Setup box and particle positions
        # Setup box and particle positions
        is_water = (units == "real" or "water" in script_text.lower() or "shake" in script_text.lower())
        is_metal = (units == "metal")

        if is_water:
            box_size = 18.0
            # 36 rigid water molecules = 108 atoms (36 Oxygen type 1, 72 Hydrogen type 2)
            num_molecules = 36
            natoms = num_molecules * 3
            mol_centers = []
            mol_dirs = []
            mol_vels = []

            # Distribute molecules in box with steric separation
            spacing = box_size / 3.5
            idx_m = 0
            for ix in range(4):
                for iy in range(3):
                    for iz in range(3):
                        if idx_m >= num_molecules:
                            break
                        mx = (ix + 0.5) * (box_size / 4.0) + (random.random() - 0.5) * 0.4
                        my = (iy + 0.5) * (box_size / 3.0) + (random.random() - 0.5) * 0.4
                        mz = (iz + 0.5) * (box_size / 3.0) + (random.random() - 0.5) * 0.4
                        mol_centers.append([mx, my, mz])

                        # Random orientation (unit vector u and normal v)
                        theta = random.uniform(0, 2 * math.pi)
                        phi = random.uniform(0, math.pi)
                        ux = math.sin(phi) * math.cos(theta)
                        uy = math.sin(phi) * math.sin(theta)
                        uz = math.cos(phi)
                        # Orthogonal vector
                        vx = -uy
                        vy = ux
                        vz = 0.0
                        vlen = math.hypot(vx, vy)
                        if vlen > 1e-4:
                            vx /= vlen
                            vy /= vlen
                        else:
                            vx, vy, vz = 1.0, 0.0, 0.0
                        mol_dirs.append(([ux, uy, uz], [vx, vy, vz]))
                        mol_vels.append([(random.random() - 0.5) * 0.18, (random.random() - 0.5) * 0.18, (random.random() - 0.5) * 0.18])
                        idx_m += 1

        else:
            # Atomic liquid (Molten metal or Lennard-Jones fluid)
            box_size = 16.2 if is_metal else 15.0
            # 108 atoms (FCC 3x3x3 x 4 basis atoms = 108)
            natoms = 108
            atom_positions = []
            atom_vels = []
            cell_size = box_size / 3.0
            fcc_basis = [
                [0.0, 0.0, 0.0],
                [0.5, 0.5, 0.0],
                [0.5, 0.0, 0.5],
                [0.0, 0.5, 0.5]
            ]
            for cx in range(3):
                for cy in range(3):
                    for cz in range(3):
                        for b in fcc_basis:
                            ax = (cx + b[0]) * cell_size + (random.random() - 0.5) * 0.15
                            ay = (cy + b[1]) * cell_size + (random.random() - 0.5) * 0.15
                            az = (cz + b[2]) * cell_size + (random.random() - 0.5) * 0.15
                            atom_positions.append([ax, ay, az])
                            atom_vels.append([(random.random() - 0.5) * 0.22, (random.random() - 0.5) * 0.22, (random.random() - 0.5) * 0.22])

        # Header output
        header_lines = [
            "# SYNTHETIC DATA - generated by the built-in visualization engine, NOT by LAMMPS.",
            "# No LAMMPS binary was found. Positions and thermo values below are illustrative",
            "# only and must not be used as simulation results.",
            f"# Run folder: {work_dir.name}",
            f"Created orthogonal box = (0 0 0) to ({box_size:.1f} {box_size:.1f} {box_size:.1f})",
            "  1 by 1 by 1 MPI processes",
            f"  {natoms} atoms",
            f"  Unit style       : {units}",
            "   Step          Temp          PotEng         TotEng          Press          Volume    "
        ]

        # Write initial header to log file and state
        log_file.write_text("\n".join(header_lines) + "\n", encoding="utf-8")
        with _run_states_lock:
            if run_id in _run_states:
                _run_states[run_id]["stdout_lines"].extend(header_lines)

        # Open dump file for appending frames
        with open(dump_file, "w", encoding="utf-8") as df_out:
            pass

        e_base = -3.36 if is_metal else (-6.5 if not is_water else -10.2)
        vol_base = box_size ** 3

        curr_temp = start_temp
        steps_list = list(range(0, n_steps + 1, step_interval))

        for step in steps_list:
            progress = step / max(1, n_steps)
            curr_temp = start_temp + (target_temp - start_temp) * (1.0 - math.exp(-3.0 * progress))
            t_fluct = max(1.0, curr_temp + (random.random() - 0.5) * (curr_temp * 0.03))
            pot_eng = e_base * natoms + (t_fluct - 300.0) * 0.05 + (random.random() - 0.5) * 8.0
            kin_eng = (3.0 / 2.0) * natoms * 8.617e-5 * t_fluct if is_metal else t_fluct * 1.5
            tot_eng = pot_eng + kin_eng
            press = (random.random() - 0.5) * 150.0 + (t_fluct / 300.0) * 50.0
            vol = vol_base + (t_fluct - 300.0) * 0.15

            # Thermo line
            thermo_line = f"{step:8d} {t_fluct:14.4f} {pot_eng:15.4f} {tot_eng:15.4f} {press:14.4f} {vol:15.4f}"

            with open(log_file, "a", encoding="utf-8") as lf_out:
                lf_out.write(thermo_line + "\n")

            step_frame_atoms = []
            frame_lines = [
                "ITEM: TIMESTEP",
                str(step),
                "ITEM: NUMBER OF ATOMS",
                str(natoms),
                "ITEM: BOX BOUNDS pp pp pp",
                f"0.0 {box_size:.6f}",
                f"0.0 {box_size:.6f}",
                f"0.0 {box_size:.6f}",
                "ITEM: ATOMS id type x y z c_atomKE"
            ]

            speed_factor = math.sqrt(t_fluct / max(1.0, start_temp))

            if is_water:
                # Update water molecules with rigid SPC/E geometry
                atom_id = 1
                for m_idx in range(num_molecules):
                    mc = mol_centers[m_idx]
                    mv = mol_vels[m_idx]
                    u, v = mol_dirs[m_idx]

                    # Molecular center diffusion
                    mc[0] = (mc[0] + mv[0] * speed_factor + (random.random() - 0.5) * 0.06) % box_size
                    mc[1] = (mc[1] + mv[1] * speed_factor + (random.random() - 0.5) * 0.06) % box_size
                    mc[2] = (mc[2] + mv[2] * speed_factor + (random.random() - 0.5) * 0.06) % box_size

                    # Rotational tumbling
                    rot_ang = (random.random() - 0.5) * 0.08 * speed_factor
                    cos_r, sin_r = math.cos(rot_ang), math.sin(rot_ang)
                    u_new = [u[0] * cos_r - v[0] * sin_r, u[1] * cos_r - v[1] * sin_r, u[2] * cos_r - v[2] * sin_r]
                    v_new = [u[0] * sin_r + v[0] * cos_r, u[1] * sin_r + v[1] * cos_r, u[2] * sin_r + v[2] * cos_r]
                    mol_dirs[m_idx] = (u_new, v_new)

                    # Oxygen position: at molecule center
                    ox, oy, oz = mc[0], mc[1], mc[2]
                    ke_o = round(max(0.01, 0.8 * (t_fluct / 300.0) + (random.random() - 0.5) * 0.05), 4)
                    frame_lines.append(f"{atom_id} 1 {ox:.4f} {oy:.4f} {oz:.4f} {ke_o:.4f}")
                    step_frame_atoms.append(AtomRecord([atom_id, 1, round(ox, 4), round(oy, 4), round(oz, 4), ke_o]))
                    atom_id += 1

                    # Hydrogen 1: r_OH = 1.000 A, theta = 109.47 deg
                    h1x = (ox + 0.586 * u_new[0] + 0.757 * v_new[0]) % box_size
                    h1y = (oy + 0.586 * u_new[1] + 0.757 * v_new[1]) % box_size
                    h1z = (oz + 0.586 * u_new[2] + 0.757 * v_new[2]) % box_size
                    ke_h1 = round(max(0.005, 0.2 * (t_fluct / 300.0) + (random.random() - 0.5) * 0.02), 4)
                    frame_lines.append(f"{atom_id} 2 {h1x:.4f} {h1y:.4f} {h1z:.4f} {ke_h1:.4f}")
                    step_frame_atoms.append(AtomRecord([atom_id, 2, round(h1x, 4), round(h1y, 4), round(h1z, 4), ke_h1]))
                    atom_id += 1

                    # Hydrogen 2: r_OH = 1.000 A, theta = 109.47 deg
                    h2x = (ox + 0.586 * u_new[0] - 0.757 * v_new[0]) % box_size
                    h2y = (oy + 0.586 * u_new[1] - 0.757 * v_new[1]) % box_size
                    h2z = (oz + 0.586 * u_new[2] - 0.757 * v_new[2]) % box_size
                    ke_h2 = round(max(0.005, 0.2 * (t_fluct / 300.0) + (random.random() - 0.5) * 0.02), 4)
                    frame_lines.append(f"{atom_id} 2 {h2x:.4f} {h2y:.4f} {h2z:.4f} {ke_h2:.4f}")
                    step_frame_atoms.append(AtomRecord([atom_id, 2, round(h2x, 4), round(h2y, 4), round(h2z, 4), ke_h2]))
                    atom_id += 1

            else:
                # Update atomic fluid (Lennard-Jones / Molten Metal)
                # Compute pairwise soft-core repulsion to preserve liquid coordination shells
                forces = [[0.0, 0.0, 0.0] for _ in range(natoms)]
                sigma = 2.4 if is_metal else 2.2
                rcut_sq = (sigma * 1.3) ** 2

                for i in range(natoms):
                    p1 = atom_positions[i]
                    for j in range(i + 1, min(natoms, i + 16)):
                        p2 = atom_positions[j]
                        dx = p1[0] - p2[0]
                        dy = p1[1] - p2[1]
                        dz = p1[2] - p2[2]
                        # Minimum image convention
                        if dx > box_size / 2: dx -= box_size
                        elif dx < -box_size / 2: dx += box_size
                        if dy > box_size / 2: dy -= box_size
                        elif dy < -box_size / 2: dy += box_size
                        if dz > box_size / 2: dz -= box_size
                        elif dz < -box_size / 2: dz += box_size

                        r2 = dx * dx + dy * dy + dz * dz
                        if 0.1 < r2 < rcut_sq:
                            r = math.sqrt(r2)
                            f_mag = 0.08 * ((sigma / r) ** 4 - 1.0)
                            fx = (dx / r) * f_mag
                            fy = (dy / r) * f_mag
                            fz = (dz / r) * f_mag
                            forces[i][0] += fx
                            forces[i][1] += fy
                            forces[i][2] += fz
                            forces[j][0] -= fx
                            forces[j][1] -= fy
                            forces[j][2] -= fz

                for a_idx in range(natoms):
                    pos = atom_positions[a_idx]
                    vel = atom_vels[a_idx]
                    f = forces[a_idx]

                    # Liquid Verlet-like position advance
                    pos[0] = (pos[0] + vel[0] * speed_factor + f[0] * 0.05 + (random.random() - 0.5) * 0.04) % box_size
                    pos[1] = (pos[1] + vel[1] * speed_factor + f[1] * 0.05 + (random.random() - 0.5) * 0.04) % box_size
                    pos[2] = (pos[2] + vel[2] * speed_factor + f[2] * 0.05 + (random.random() - 0.5) * 0.04) % box_size

                    v_sq = vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2
                    f_mag = math.sqrt(f[0] ** 2 + f[1] ** 2 + f[2] ** 2)

                    if units == "lj":
                        ke_val = round(max(0.05, 0.5 * v_sq * (t_fluct / max(0.1, start_temp)) + (random.random() - 0.5) * 0.1), 4)
                    elif units == "metal":
                        ke_val = round(max(0.005, 0.08 * (t_fluct / 300.0) + (random.random() - 0.5) * 0.02), 4)
                    else:
                        ke_val = round(max(0.05, 0.9 * (t_fluct / 300.0) + (random.random() - 0.5) * 0.15), 4)

                    frame_lines.append(f"{a_idx + 1} 1 {pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f} {ke_val:.4f}")
                    step_frame_atoms.append(AtomRecord([
                        a_idx + 1,
                        1,
                        round(pos[0], 4),
                        round(pos[1], 4),
                        round(pos[2], 4),
                        ke_val
                    ]))

            # Append frame to dump.lammpstrj file
            with open(dump_file, "a", encoding="utf-8") as df_out:
                df_out.write("\n".join(frame_lines) + "\n")

            # Update live state
            with _run_states_lock:
                if run_id in _run_states:
                    _run_states[run_id]["stdout_lines"].append(thermo_line)
                    _run_states[run_id]["frames"].append({
                        "timestep": step,
                        "natoms": natoms,
                        "box": [[0.0, box_size], [0.0, box_size], [0.0, box_size]],
                        "columns": ["id", "type", "x", "y", "z", "ke"],
                        "has_ke": True,
                        "has_stress": False,
                        "atoms": step_frame_atoms
                    })
                    _run_states[run_id]["last_dump_offset"] = dump_file.stat().st_size

            time.sleep(0.04)

        # Footer lines
        footer_lines = [
            f"Loop time of {time.time() - start_time:.3f} (synthetic engine) for {n_steps} steps with {natoms} atoms",
            "# END OF SYNTHETIC DATA - not a LAMMPS result."
        ]
        with open(log_file, "a", encoding="utf-8") as lf_out:
            lf_out.write("\n".join(footer_lines) + "\n")

        with _run_states_lock:
            if run_id in _run_states:
                _run_states[run_id]["stdout_lines"].extend(footer_lines)

        # Render with OVITO
        render_res = render_final_frame(dump_file, render_file, units=units)

        # Parse thermo data
        thermo_data = self.thermo_parser.parse_log(log_file) if log_file.exists() else {}

        elapsed = time.time() - start_time

        with _run_states_lock:
            if run_id in _run_states:
                _run_states[run_id].update({
                    "status": "completed",
                    "returncode": 0,
                    "error": None,
                    "runtime_seconds": round(elapsed, 3),
                    "thermo": thermo_data,
                    "render_result": render_res
                })

        # Save to SQLite memory
        try:
            self.memory.save_simulation_run(
                run_id=run_id,
                conv_id=conversation_id,
                script=script_text,
                ret_code=0,
                runtime=round(elapsed, 3),
                summary=thermo_data.get("summary", {}) if isinstance(thermo_data, dict) else {}
            )
        except Exception:
            pass
