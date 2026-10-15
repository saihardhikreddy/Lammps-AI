"""Scientific and Syntax Validation Engine for LAMMPS Scripts."""
from typing import List, Dict, Any, Optional
import re

def is_escaping_path(token: str) -> bool:
    """True if a script token looks like a file path outside the working directory."""
    t = token.strip("\"'")
    if re.match(r"^/[A-Za-z0-9_.~-]", t) or t.startswith("~/") or t.startswith("\\\\"):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", t):
        return True
    parts = t.replace("\\", "/").split("/")
    return len(parts) > 1 and ".." in parts


class ScriptValidator:
    """Performs deep static rule-based & scientific sanity validation of LAMMPS scripts."""

    def validate_static(self, script_text: str) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []
        assumptions: List[str] = []
        commands_found: List[str] = []

        lines = [line.strip() for line in script_text.splitlines()]
        clean_lines = []
        for line in lines:
            # strip comments
            code = line.split('#')[0].strip()
            if code:
                clean_lines.append(code)

        if not clean_lines:
            return {
                "valid": False,
                "executable": False,
                "errors": ["Script is empty."],
                "warnings": [],
                "assumptions": [],
                "commands": []
            }

        units_style = None
        has_atom_style = False
        has_boundary = False
        has_box_or_data = False
        has_pair_style = False
        has_pair_coeff = False
        has_fix = False
        has_integrating_fix = False
        has_atoms = False
        has_velocity = False
        has_timestep = False
        has_thermo = False
        has_run = False
        has_minimize = False
        timestep_val = None

        integrator_styles = {"nve", "nvt", "npt", "nph", "langevin", "rigid", "nvt/sphere", "nve/sphere"}

        for line in clean_lines:
            tokens = line.split()
            cmd = tokens[0].lower()
            commands_found.append(cmd)

            if cmd == "units" and len(tokens) > 1:
                units_style = tokens[1].lower()
                assumptions.append(f"Units system: '{units_style}'")
            elif cmd == "atom_style":
                has_atom_style = True
            elif cmd == "boundary":
                has_boundary = True
                assumptions.append(f"Boundary conditions: {' '.join(tokens[1:])}")
            elif cmd in ("create_box", "read_data", "read_restart"):
                has_box_or_data = True
            elif cmd in ("create_atoms", "read_data", "read_restart"):
                has_atoms = True
            elif cmd == "velocity":
                has_velocity = True
            elif cmd == "pair_style":
                has_pair_style = True
                assumptions.append(f"Pair potential style: {' '.join(tokens[1:])}")
            elif cmd == "pair_coeff":
                has_pair_coeff = True
            elif cmd == "fix":
                has_fix = True
                if len(tokens) > 3:
                    style_tok = tokens[3].lower()
                    if style_tok in integrator_styles or any(style_tok.startswith(s) for s in ["nvt", "npt", "nve", "langevin"]):
                        has_integrating_fix = True
            elif cmd in ("thermo", "thermo_style"):
                has_thermo = True
            elif cmd == "run":
                has_run = True
            elif cmd == "minimize":
                has_minimize = True
            elif cmd == "timestep" and len(tokens) > 1:
                has_timestep = True
                try:
                    timestep_val = float(tokens[1])
                except ValueError:
                    errors.append(f"Invalid timestep value: '{tokens[1]}'")

        # 1. Structural requirements
        if not units_style:
            errors.append("Missing 'units' declaration (e.g., 'units metal', 'units real', 'units lj').")
        if not has_atom_style and "read_data" not in commands_found and "read_restart" not in commands_found:
            warnings.append("No 'atom_style' specified prior to box/data creation.")
        if not has_boundary:
            warnings.append("No explicit 'boundary' specified (LAMMPS defaults to 'p p p').")
        if not has_box_or_data:
            errors.append("No simulation box defined (missing 'create_box', 'read_data', or 'read_restart').")
        if has_box_or_data and not has_atoms and not has_minimize:
            errors.append("Simulation box created but no atoms added (missing 'create_atoms', 'read_data', or 'read_restart').")

        # 2. Force field / interaction integrity
        if has_pair_style and not has_pair_coeff and "read_data" not in commands_found:
            errors.append("Defined 'pair_style' but missing corresponding 'pair_coeff' interactions.")
        if not has_pair_style and "read_data" not in commands_found:
            warnings.append("No 'pair_style' defined. System may have zero non-bonded interatomic forces.")

        # 3. Time integration & execution integrity
        if not has_integrating_fix and not has_minimize:
            warnings.append("No active time-integrating 'fix' (e.g. 'fix 1 all nve', 'fix 1 all nvt'). Atoms will not undergo numerical time integration during dynamics.")
        if not has_run and not has_minimize:
            warnings.append("Script contains no 'run' or 'minimize' execution directive.")

        # 4. Liquid velocity & thermal state checks (Issue #18)
        if has_run and not has_velocity and "read_data" not in commands_found and "read_restart" not in commands_found:
            warnings.append("No explicit 'velocity' command found before dynamics. Liquid atoms starting from rest at 0 K fail to represent an equilibrated thermal state.")

        # 5. Timestep specification & safety checks (Issue #18)
        if not has_timestep:
            warnings.append("No explicit 'timestep' set in script; relying on LAMMPS default value.")
            if units_style:
                default_dt = 0.001 if units_style == "metal" else (1.0 if units_style == "real" else 0.005)
                assumptions.append(f"Timestep: default {default_dt} ({units_style} units)")

        if units_style == "metal" and timestep_val is not None:
            if timestep_val > 0.003:  # > 3 fs in metal ps units
                warnings.append(f"Timestep {timestep_val} ps is high for metal units (> 0.003 ps / 3 fs). Risk of energy drift or lost atoms.")
        elif units_style == "real" and timestep_val is not None:
            if timestep_val > 2.5:  # > 2.5 fs
                warnings.append(f"Timestep {timestep_val} fs in real units is dangerously high (> 2.5 fs for flexible bonds/water).")
        elif units_style == "lj" and timestep_val is not None:
            if timestep_val > 0.005:
                warnings.append(f"Timestep {timestep_val} tau exceeds the usual LJ stability limit of 0.005 tau.")

        # 6. Topology & charge consistency (catches "water" boxes with no molecules)
        has_topology_source = any(c in commands_found for c in ("read_data", "read_restart", "molecule", "create_bonds"))
        has_charge_source = has_topology_source or any(
            l.split()[0].lower() == "set" and " charge " in f" {l.lower()} " for l in clean_lines)
        if "kspace_style" in commands_found and not has_charge_source:
            errors.append("kspace_style is set but no atom charges are defined (no read_data, molecule template, "
                          "or 'set ... charge'); the long-range solver would act on an uncharged system.")
        for l in clean_lines:
            toks = l.split()
            if toks[0].lower() == "fix" and len(toks) > 3 and toks[3].lower() in ("shake", "rattle") \
                    and not has_topology_source:
                errors.append(f"fix {toks[3].lower()} constrains bonds/angles, but no bonds exist (no read_data, "
                              f"molecule template, or create_bonds).")

        # 7. Transport measured under a thermostat (biased dynamics)
        measures_transport = any(
            (l.split()[0].lower() == "compute" and len(l.split()) > 3 and l.split()[3].lower() in ("msd", "vacf"))
            or (l.split()[0].lower() == "fix" and len(l.split()) > 3 and l.split()[3].lower() == "ave/correlate")
            for l in clean_lines)
        if measures_transport:
            active: Dict[str, str] = {}
            last_active_at_run: Dict[str, str] = {}
            for l in clean_lines:
                toks = l.split()
                c = toks[0].lower()
                if c == "fix" and len(toks) > 3:
                    active[toks[1]] = toks[3].lower()
                elif c == "unfix" and len(toks) > 1:
                    active.pop(toks[1], None)
                elif c == "run":
                    last_active_at_run = dict(active)
            thermostats = {st for st in last_active_at_run.values()
                           if st.startswith(("nvt", "npt", "langevin", "temp/", "nph"))}
            if thermostats:
                warnings.append(f"Transport properties (MSD / Green-Kubo) are sampled while a thermostat or barostat "
                                f"is active ({', '.join(sorted(thermostats))}); this perturbs the dynamics. "
                                f"Use NVE for the production run.")

        # 8. File paths must stay inside the run folder
        for l in clean_lines:
            for tok in l.split()[1:]:
                t = tok.strip("\"'")
                if is_escaping_path(t):
                    errors.append(f"File path '{t}' points outside the run folder; only plain relative "
                                  f"file names are allowed.")
                    break

        is_valid = len(errors) == 0
        return {
            "valid": is_valid,
            "executable": is_valid,
            "errors": errors,
            "warnings": warnings,
            "assumptions": assumptions,
            "commands": list(set(commands_found))
        }
