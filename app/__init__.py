"""Package initialization and optional virtual-environment discovery for Linux/POSIX.

If the app is started with the system Python, site-packages from a nearby virtual
environment (for optional extras such as ovito or google-genai) are added to sys.path.
Only environments built for the *same* Python major.minor version are used; loading
compiled packages from a different interpreter version fails in confusing ways.
"""
import sys
from pathlib import Path

_py_dir = f"python{sys.version_info.major}.{sys.version_info.minor}"
_possible_venv_roots = [
    Path.home() / ".venv",
    Path(__file__).resolve().parent.parent / ".venv",
    Path.home() / ".local" / "share" / "lammps-venv"
]

for _vroot in _possible_venv_roots:
    _sp = _vroot / "lib" / _py_dir / "site-packages"
    if _sp.is_dir() and str(_sp) not in sys.path:
        sys.path.append(str(_sp))
