"""Optional local OVITO post-run rendering and coordination analysis with process isolation."""
import os
import sys
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

UNIT_DEFAULT_CUTOFFS = {
    "lj": 1.5,
    "real": 3.35,
    "metal": 3.4,
    "electron": 3.0,
    "si": 0.35e-9,
    "cgs": 0.35e-7,
    "nano": 0.35,
    "micro": 0.00035,
}
DEFAULT_CUTOFF = 3.5


def detect_units(dump_path: Path, units: Optional[str] = None) -> str:
    """Detects the LAMMPS unit style (e.g. 'lj', 'metal', 'real') for a given trajectory.

    Priority:
    1. Explicit units argument if provided.
    2. Input scripts in the dump directory (in.run, *.in, in.*) for 'units <style>'.
    3. log.lammps in the dump directory for 'Unit style : <style>' or 'units <style>'.
    4. Defaults to 'metal' if undetected.
    """
    if units and isinstance(units, str) and units.strip():
        return units.strip().lower()

    parent = dump_path.parent if dump_path else None
    if parent and parent.exists():
        # 1. Search input scripts
        script_candidates = list(parent.glob("in.run")) + list(parent.glob("*.in")) + list(parent.glob("in.*"))
        for s_file in script_candidates:
            try:
                content = s_file.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    line = line.split("#")[0].strip()
                    m = re.match(r"^units\s+([a-zA-Z0-9_]+)", line, re.IGNORECASE)
                    if m:
                        return m.group(1).lower()
            except Exception:
                pass

        # 2. Search log.lammps
        log_file = parent / "log.lammps"
        if log_file.exists():
            try:
                content = log_file.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    m_style = re.search(r"Unit style\s*:\s*([a-zA-Z0-9_]+)", line, re.IGNORECASE)
                    if m_style:
                        return m_style.group(1).lower()
                    m_units = re.match(r"^\s*units\s+([a-zA-Z0-9_]+)", line.split("#")[0].strip(), re.IGNORECASE)
                    if m_units:
                        return m_units.group(1).lower()
            except Exception:
                pass

    return "metal"


def find_first_rdf_minimum(
    r_arr: Any,
    gr_arr: Any,
    units: str
) -> Optional[float]:
    """Finds the first minimum in g(r) following the first coordination peak.

    Args:
        r_arr: 1D array of radial distances.
        gr_arr: 1D array of pair correlation g(r) values.
        units: LAMMPS unit style string (e.g. 'lj', 'real', 'metal').

    Returns:
        The radial distance of the first minimum rounded to 2 decimal places,
        or None if no physically valid minimum could be identified.
    """
    try:
        import numpy as np
        r_np = np.asarray(r_arr, dtype=float)
        gr_np = np.asarray(gr_arr, dtype=float)
    except Exception:
        return None

    if len(r_np) < 8 or len(gr_np) < 8:
        return None

    units_clean = (units or "").strip().lower()
    if units_clean == "lj":
        min_r, max_r = 1.20, 1.85
    elif units_clean == "real":
        min_r, max_r = 2.80, 4.20
    elif units_clean == "metal":
        min_r, max_r = 2.80, 4.20
    else:
        min_r, max_r = 2.50, 4.50

    # Smooth gr with a 5-point boxcar to eliminate discrete binning noise
    kernel_size = min(5, len(gr_np))
    kernel = np.ones(kernel_size) / float(kernel_size)
    gr_smooth = np.convolve(gr_np, kernel, mode="same")

    # Verify that a prominent first peak exists before or in the search window
    peak_mask = r_np <= max_r
    if not np.any(peak_mask):
        return None
    r_peak_zone = r_np[peak_mask]
    gr_peak_zone = gr_smooth[peak_mask]
    if len(gr_peak_zone) == 0 or np.max(gr_peak_zone) < 1.05:
        return None

    # Search window for the first minimum
    window_mask = (r_np >= min_r) & (r_np <= max_r)
    if not np.any(window_mask):
        return None

    r_window = r_np[window_mask]
    gr_window = gr_smooth[window_mask]
    min_idx = int(np.argmin(gr_window))
    min_val = float(gr_window[min_idx])

    max_val = float(np.max(gr_peak_zone))
    if min_val >= max_val:
        return None

    return round(float(r_window[min_idx]), 2)


def _render_direct(
    dump_path: Path,
    output_png: Path,
    coordination_cutoff: Optional[float] = None,
    units: Optional[str] = None
) -> Dict[str, Any]:
    """Internal direct worker executing within an isolated process context."""
    if not dump_path.exists():
        return {
            "available": False,
            "reason": f"Trajectory dump file not found: {dump_path}"
        }

    try:
        # Isolated import — ovito is in requirements-visualization.txt
        import ovito
        from ovito.io import import_file
        from ovito.modifiers import CoordinationAnalysisModifier, ColorCodingModifier
        from ovito.vis import Viewport, TachyonRenderer

        detected_units = detect_units(dump_path, units)
        pipeline = import_file(str(dump_path.resolve()))

        num_frames = pipeline.num_frames
        if num_frames <= 0:
            return {
                "available": False,
                "reason": "Trajectory contains zero frames."
            }

        last_frame_idx = num_frames - 1

        # Determine coordination cutoff (user-specified vs. unit-aware / RDF-derived)
        if coordination_cutoff is not None and coordination_cutoff > 0:
            effective_cutoff = float(coordination_cutoff)
            cutoff_source = "user_specified"
            coord_mod = CoordinationAnalysisModifier(cutoff=effective_cutoff, number_of_bins=50)
            pipeline.modifiers.append(coord_mod)
        else:
            probe_cutoff = 2.5 if detected_units == "lj" else 6.0
            fallback_cutoff = UNIT_DEFAULT_CUTOFFS.get(detected_units, DEFAULT_CUTOFF)
            coord_mod = CoordinationAnalysisModifier(cutoff=probe_cutoff, number_of_bins=100)
            pipeline.modifiers.append(coord_mod)
            probe_data = pipeline.compute(last_frame_idx)

            derived_cutoff = None
            if hasattr(probe_data, "tables") and "coordination-rdf" in probe_data.tables:
                xy = probe_data.tables["coordination-rdf"].xy()
                derived_cutoff = find_first_rdf_minimum(xy[:, 0], xy[:, 1], detected_units)

            if derived_cutoff is not None:
                effective_cutoff = derived_cutoff
                cutoff_source = "rdf_first_minimum"
            else:
                effective_cutoff = fallback_cutoff
                cutoff_source = f"unit_default_{detected_units}"

            coord_mod.cutoff = effective_cutoff
            coord_mod.number_of_bins = 50

        # Modifier: Color coding by coordination number
        color_mod = ColorCodingModifier(property="Coordination")
        pipeline.modifiers.append(color_mod)

        # Evaluate last frame
        data = pipeline.compute(last_frame_idx)

        # Extract coordination histogram
        coord_hist: Dict[int, int] = {}
        if hasattr(data, "particles") and "Coordination" in data.particles:
            coords = data.particles["Coordination"]
            for c in coords:
                bin_val = int(round(float(c)))
                coord_hist[bin_val] = coord_hist.get(bin_val, 0) + 1

        # Render viewport to PNG using CPU TachyonRenderer (avoids GPU Vulkan/OpenGL driver crashes)
        pipeline.add_to_scene()
        output_png.parent.mkdir(parents=True, exist_ok=True)
        vp = Viewport(type=Viewport.Type.Perspective)
        vp.zoom_all()
        renderer = TachyonRenderer()
        vp.render_image(filename=str(output_png.resolve()), size=(800, 600), frame=last_frame_idx, renderer=renderer)

        return {
            "available": True,
            "image_path": str(output_png.resolve()),
            "coordination_histogram": coord_hist,
            "coordination_cutoff": effective_cutoff,
            "cutoff_source": cutoff_source,
            "units": detected_units,
            "num_particles": data.particles.count if hasattr(data, "particles") else 0,
            "rendered_frame": last_frame_idx
        }

    except ImportError:
        return {
            "available": False,
            "reason": "OVITO is not installed. To enable high-fidelity offline rendering, install requirements-visualization.txt."
        }
    except Exception as e:
        return {
            "available": False,
            "reason": f"OVITO rendering failed ({type(e).__name__}): {str(e)}"
        }


def render_final_frame(
    dump_path: Path,
    output_png: Path,
    coordination_cutoff: Optional[float] = None,
    units: Optional[str] = None,
    isolate_process: bool = True
) -> Dict[str, Any]:
    """Renders the final trajectory frame and calculates the unit-aware coordination histogram using OVITO.

    Uses process isolation to ensure Qt / graphics runtime objects are isolated from the main server
    thread, preventing thread-affinity issues and driver segmentation faults.

    Args:
        dump_path: Path to the input dump.lammpstrj file.
        output_png: Path where the rendered PNG image should be written.
        coordination_cutoff: Optional explicit radial cutoff. If None, derived dynamically
                            from the first minimum of g(r) or unit system defaults.
        units: LAMMPS unit style (e.g. 'lj', 'real', 'metal'). If None, auto-detected.
        isolate_process: If True, executes the render in an isolated subprocess.

    Returns:
        Dict with "available": True/False, and analysis metadata or reason for failure.
    """
    if not dump_path.exists():
        return {
            "available": False,
            "reason": f"Trajectory dump file not found: {dump_path}"
        }

    # If already running inside an isolated child worker, execute directly
    if not isolate_process or os.environ.get("OVITO_ISOLATED_WORKER") == "1":
        return _render_direct(dump_path, output_png, coordination_cutoff, units)

    # Spawn isolated worker process
    cutoff_param = repr(coordination_cutoff)
    units_param = repr(units)
    worker_script = f"""
import os, sys, json
from pathlib import Path
os.environ['OVITO_ISOLATED_WORKER'] = '1'
from app.lammps.ovito_renderer import _render_direct
res = _render_direct(Path({repr(str(dump_path.resolve()))}), Path({repr(str(output_png.resolve()))}), coordination_cutoff={cutoff_param}, units={units_param})
print("__OVITO_RESULT__" + json.dumps(res))
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", worker_script],
            capture_output=True,
            text=True,
            timeout=40,
            env={**os.environ, "OVITO_ISOLATED_WORKER": "1"}
        )
        for line in proc.stdout.splitlines():
            if line.startswith("__OVITO_RESULT__"):
                return json.loads(line[len("__OVITO_RESULT__"):])

        if proc.returncode != 0:
            return {
                "available": False,
                "reason": f"OVITO worker process exited with code {proc.returncode}: {proc.stderr.strip()}"
            }
        return {
            "available": False,
            "reason": "OVITO worker did not return structured result."
        }
    except Exception as e:
        return {
            "available": False,
            "reason": f"OVITO worker execution error ({type(e).__name__}): {str(e)}"
        }
