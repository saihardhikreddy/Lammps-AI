"""Parameter runs for a fixed set of lecturer scripts (simulations/param_scripts/<id>/).

Each script's editable parameters are its own `variable NAME equal|index|string VALUE`
lines before the first run/minimize. A student's value is validated and written only
into the value slot of that line (style kept); `lmp -var` is never used. The rendered
copy is written into the run folder only - the files in param_scripts/ never change.
"""
import math
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import SIMULATIONS_DIR
from app.lammps.validator import is_escaping_path

PARAM_SCRIPTS_DIR = SIMULATIONS_DIR / "param_scripts"

# The runs offered in the "Parameter Runs" tab: id -> folder and input script name.
SCRIPTS: Dict[str, Dict[str, str]] = {
    "active-liquid": {
        "title": "Active liquid - 1000 self-propelled discs (2D)",
        "folder": "active-liquid",
        "script": "in.activeliquid",
    },
}

# Shown but not editable: the data file and output names the app relies on
# (the 3D viewer only reads dump.lammpstrj).
LOCKED = {"input", "dumpfile", "output"}

NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
INT_RE = re.compile(r"^[+-]?\d+$")
SAFE_RE = re.compile(r"^[A-Za-z0-9_.\-/]{1,64}$")
VAR_RE = re.compile(r"^(\s*variable\s+(\w+)\s+(equal|index|string)\s+)(\S+)(.*)$", re.IGNORECASE)
COORDS = (("x", "y", "z"), ("xu", "yu", "zu"), ("xs", "ys", "zs"))


class ParamError(ValueError):
    def __init__(self, errors: Dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _code(line: str) -> str:
    return line.split("#", 1)[0].strip()


def detect_variables(text: str) -> List[Dict[str, Any]]:
    """Literal, single-line variable definitions before the first run/minimize."""
    found: List[Dict[str, Any]] = []
    for i, line in enumerate(text.splitlines()):
        code = _code(line)
        if code.split()[:1] and code.split()[0].lower() in ("run", "minimize"):
            break
        m = VAR_RE.match(line)
        if not m or line.rstrip().endswith("&"):
            continue
        name, style, value = m.group(2), m.group(3).lower(), m.group(4).strip("\"'")
        if NUMBER_RE.match(value):
            kind = "int" if INT_RE.match(value) else "float"
        elif SAFE_RE.match(value) and "$" not in value and not value.startswith(("v_", "c_", "f_")):
            kind = "string"
        else:
            continue  # formula / reference (next(nf), -c_myVirial[1], ...): not a parameter
        comment = line.split("#", 1)[1].strip() if "#" in line else ""
        found.append({"name": name, "style": style, "type": kind, "default": value, "line": i + 1,
                      "label": comment, "editable": name not in LOCKED})
    return found


def find_viewer_dump(text: str) -> Dict[str, Any]:
    """Report whether a dump the 3D viewer can read (id type x y z) exists. Nothing is added."""
    for line in text.splitlines():
        toks = _code(line).split()
        if len(toks) >= 6 and toks[0] == "dump" and toks[3] in ("custom", "atom"):
            cols = [c.lower() for c in toks[6:]]
            if toks[3] == "atom" or any(all(c in cols for c in cs) for cs in COORDS):
                return {"ok": True, "message": None}
            if "x" in cols and "y" in cols:
                return {"ok": True, "message": (
                    f"The dump '{toks[1]}' has x and y but no z column (a 2D run): "
                    f"the 3D viewer shows the atoms in the xy plane.")}
    return {"ok": False, "message": "This script has no dump with x y z coordinates, so the 3D viewer will "
                                   "stay empty. The console and thermo output still work."}


def _entry(script_id: str) -> Tuple[Dict[str, str], Path, str]:
    if script_id not in SCRIPTS:
        raise KeyError(script_id)
    meta = SCRIPTS[script_id]
    folder = PARAM_SCRIPTS_DIR / meta["folder"]
    return meta, folder, (folder / meta["script"]).read_text(encoding="utf-8")


def list_scripts() -> List[Dict[str, Any]]:
    out = []
    for sid, meta in SCRIPTS.items():
        try:
            _, folder, text = _entry(sid)
        except OSError as e:
            out.append({"id": sid, "title": meta["title"], "error": f"Script file missing: {e}"})
            continue
        out.append({"id": sid, "title": meta["title"], "file": meta["script"], "source": text,
                    "variables": detect_variables(text), "viewer": find_viewer_dump(text),
                    "files": sorted(p.name for p in folder.iterdir() if p.is_file())})
    return out


def validate(variables: List[Dict[str, Any]], params: Dict[str, Any]) -> Dict[str, str]:
    """Return name -> text to write for every changed parameter. Raises ParamError."""
    if not isinstance(params, dict):
        raise ParamError({"params": "must be an object"})
    by_name = {v["name"]: v for v in variables}
    errors: Dict[str, str] = {}
    out: Dict[str, str] = {}
    for name, value in params.items():
        var = by_name.get(name)
        if var is None:
            errors[str(name)[:64]] = "unknown parameter"
            continue
        if isinstance(value, bool) or value is None or isinstance(value, (list, dict)):
            errors[name] = "invalid value"
            continue
        text = str(value).strip() if isinstance(value, str) else repr(value)
        if var["type"] in ("int", "float"):
            if not NUMBER_RE.match(text):
                errors[name] = "must be a number"
                continue
            x = float(text)
            if not math.isfinite(x):
                errors[name] = "must be a finite number"
                continue
            if var["type"] == "int" and not x.is_integer():
                errors[name] = "must be a whole number"
                continue
            if x == float(var["default"]):
                continue  # unchanged (e.g. "1" vs "1.0")
            text = str(int(x)) if var["type"] == "int" else format(x, ".12g")
        else:
            if not SAFE_RE.match(text) or text in (".", "..") or is_escaping_path(text) or ".." in text.split("/"):
                errors[name] = "only letters, digits and _ . - / allowed; relative paths only"
                continue
            if text == var["default"]:
                continue
        if not var["editable"]:
            errors[name] = "this parameter is fixed"
            continue
        out[name] = text
    if errors:
        raise ParamError(errors)
    return out


def render(text: str, variables: List[Dict[str, Any]], changes: Dict[str, str]) -> Tuple[str, List[int]]:
    """Rewrite only the value slot of each changed variable line. Returns (text, changed 1-based lines)."""
    lines = text.split("\n")
    changed = []
    for var in variables:
        if var["name"] not in changes:
            continue
        idx = var["line"] - 1
        m = VAR_RE.match(lines[idx])
        assert m and m.group(2) == var["name"]
        lines[idx] = m.group(1) + changes[var["name"]] + m.group(5)
        changed.append(var["line"])
    return "\n".join(lines), changed


def prepare(script_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Validate + render one script. Raises KeyError (unknown id) or ParamError."""
    meta, folder, text = _entry(script_id)
    variables = detect_variables(text)
    changes = validate(variables, params)
    rendered, changed = render(text, variables, changes)
    return {"id": script_id, "meta": meta, "folder": folder, "text": rendered, "changed_lines": changed,
            "viewer": find_viewer_dump(text)}


def stage_run_folder(prepared: Dict[str, Any], work_dir: Path) -> Path:
    """Copy the script's data files and the rendered script into the run folder."""
    work_dir.mkdir(parents=True, exist_ok=True)
    for src in prepared["folder"].iterdir():
        if src.is_file() and not src.is_symlink() and src.name != prepared["meta"]["script"]:
            shutil.copy2(src, work_dir / src.name)
    script_path = work_dir / ("param." + prepared["meta"]["script"])
    script_path.write_text(prepared["text"], encoding="utf-8")
    return script_path
