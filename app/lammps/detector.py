"""Local LAMMPS Executable Detection and Capabilities Inspection."""
import shutil
import subprocess
import os
import glob
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import LAMMPS_EXECUTABLE

_CACHED_DETECTION: Optional[Dict[str, Any]] = None

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

    # Check system PATH
    candidates.extend(["lmp", "lmp.exe", "lmp_serial", "lmp_mpi", "lammps", "lmp_daily"])

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

    found_path = None
    for name in candidates:
        resolved = shutil.which(name)
        if resolved:
            found_path = resolved
            break
        elif os.path.isfile(name) and (name.lower().endswith(".exe") or os.access(name, os.X_OK)):
            found_path = name
            break

    if not found_path:
        res = {
            "detected": False,
            "executable": None,
            "version": "Not Detected (Local offline docs & script generator active)",
            "packages": [],
            "status_text": "LAMMPS: NOT DETECTED"
        }
        if not custom_path:
            _CACHED_DETECTION = res
        return res

    # Query LAMMPS version and installed packages safely
    version = "Unknown"
    packages = []
    try:
        res_proc = subprocess.run([found_path, "-help"], capture_output=True, text=True, timeout=5)
        stdout = res_proc.stdout
        for line in stdout.splitlines():
            if "LAMMPS (" in line or "Large-scale Atomic" in line:
                version = line.strip()
            if "Installed packages:" in line or "Package " in line:
                packages.append(line.strip())
        if version == "Unknown" and stdout:
            first_line = stdout.splitlines()[0].strip() if stdout.splitlines() else ""
            if first_line:
                version = first_line
    except Exception:
        version = f"Detected ({found_path})"

    res = {
        "detected": True,
        "executable": found_path,
        "version": version,
        "packages": packages,
        "status_text": f"LAMMPS: DETECTED ({os.path.basename(found_path)})"
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

