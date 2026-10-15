"""Local LAMMPS Executable Detection and Capabilities Inspection."""
import shutil
import subprocess
import os
import glob
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import LAMMPS_EXECUTABLE

_CACHED_DETECTION: Optional[Dict[str, Any]] = None

def parse_installed_packages(help_text: str) -> list:
    """Extract package names from `lmp -help` output.

    The names follow an "Installed packages:" header, wrapped over several lines and
    terminated by a blank line (after at least one line of names).
    """
    packages = []
    in_block = False
    for raw in help_text.replace("\x00", "").splitlines():
        line = raw.strip()
        if not in_block:
            if line.startswith("Installed packages:"):
                in_block = True
            continue
        if not line:
            if packages:
                break
            continue
        if line.endswith(":") or line.lower().startswith("list of"):
            break
        packages.extend(tok for tok in line.split() if tok.replace("-", "").replace("_", "").isalnum())
    return packages


def detect_lammps(custom_path: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """Detect local LAMMPS binaries and report version and package capabilities (cached)."""
    global _CACHED_DETECTION
    if _CACHED_DETECTION is not None and not custom_path and not force_refresh:
        return _CACHED_DETECTION

    candidates = []
    if custom_path and custom_path.strip():
        candidates.append(custom_path.strip())
    if LAMMPS_EXECUTABLE and LAMMPS_EXECUTABLE.strip():
        candidates.append(LAMMPS_EXECUTABLE.strip())

    # Check system PATH and standard Linux/Unix paths
    candidates.extend(["lmp", "lmp.exe", "lmp_serial", "lmp_mpi", "lammps", "lmp_daily"])
    user_home = Path.home()
    linux_candidates = [
        str(user_home / ".local" / "bin" / "lmp"),
        str(user_home / ".local" / "lammps-env" / "bin" / "lmp"),
        "/usr/local/bin/lmp",
        "/usr/bin/lmp",
        "/opt/lammps/bin/lmp"
    ]
    candidates.extend([p for p in linux_candidates if os.path.exists(p)])

    # Check standard Windows installation directories
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    user_profile = os.environ.get("USERPROFILE", "")

    search_patterns = [
        os.path.join(local_app_data, "LAMMPS*", "bin", "lmp.exe"),
        os.path.join(user_profile, "AppData", "Local", "LAMMPS*", "bin", "lmp.exe"),
        os.path.join(program_files, "LAMMPS*", "bin", "lmp.exe"),
        "C:\\LAMMPS*\\bin\\lmp.exe"
    ]

    for pat in search_patterns:
        matches = glob.glob(pat)
        if matches:
            candidates.extend(sorted(matches, reverse=True))

    is_wsl = False
    found_path = None
    for name in candidates:
        resolved = shutil.which(name)
        if resolved:
            found_path = resolved
            break
        elif os.path.isfile(name) and (name.lower().endswith(".exe") or os.access(name, os.X_OK)):
            found_path = name
            break

    # If no Windows binary, check WSL2 Ubuntu
    if not found_path and shutil.which("wsl"):
        try:
            wsl_check = subprocess.run(
                ["wsl", "-d", "Ubuntu", "--cd", "~", "bash", "-c", "which lmp lmp_serial lmp_mpi lammps 2>/dev/null"],
                capture_output=True,
                text=True,
                timeout=12
            )
            clean_out = wsl_check.stdout.replace("\x00", "")
            lines = [l.strip() for l in clean_out.splitlines() if l.strip() and not l.startswith("wsl:")]
            valid_paths = [l for l in lines if l.startswith("/") and " " not in l]
            if valid_paths:
                found_path = f"wsl:{valid_paths[0]}"
                is_wsl = True
        except Exception:
            pass

    if not found_path:
        return {
            "detected": False,
            "executable": None,
            "version": "Not Detected (Local offline docs & script generator active)",
            "packages": [],
            "status_text": "LAMMPS: NOT DETECTED"
        }

    # Query LAMMPS version and installed packages safely
    version = "Unknown"
    packages = []
    try:
        if is_wsl:
            wsl_bin = found_path.split(":", 1)[1]
            cmd = ["wsl", "-d", "Ubuntu", "--cd", "~", wsl_bin, "-help"]
        else:
            cmd = [found_path, "-help"]
        res_proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        stdout = res_proc.stdout
        for line in stdout.splitlines():
            if "LAMMPS (" in line or "Large-scale Atomic" in line:
                version = line.strip() + (" [WSL2 Ubuntu]" if is_wsl else "")
                break
        packages = parse_installed_packages(stdout)
        if version == "Unknown" and stdout:
            first_lines = [l.strip() for l in stdout.splitlines() if l.strip() and not l.startswith("wsl:")]
            if first_lines:
                version = first_lines[0] + (" [WSL2 Ubuntu]" if is_wsl else "")
    except Exception:
        version = f"Detected ({found_path})"

    exe_label = f"WSL2 Ubuntu {found_path.split(':', 1)[1]}" if is_wsl else os.path.basename(found_path)
    res = {
        "detected": True,
        "executable": found_path,
        "version": version,
        "packages": packages,
        "status_text": f"LAMMPS: DETECTED ({exe_label})"
    }
    if not custom_path:
        _CACHED_DETECTION = res
    return res

def check_lammps_version() -> str:
    det = detect_lammps()
    return det.get("version", "Not Installed")

def check_available_packages() -> list:
    det = detect_lammps()
    return det.get("packages", [])

