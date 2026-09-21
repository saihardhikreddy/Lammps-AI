"""Scientific and Syntax Validation Engine for LAMMPS Scripts."""
from typing import List, Dict, Any, Optional
import re

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
        has_timestep = False
        has_thermo = False
        has_run_or_minimize = False
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
            elif cmd == "pair_style":
                has_pair_style = True
                assumptions.append(f"Pair potential style: {' '.join(tokens[1:])}")
            elif cmd == "pair_coeff":
                has_pair_coeff = True
            elif cmd == "fix":
                has_fix = True
                if len(tokens) > 3 and tokens[3].lower() in integrator_styles:
                    has_integrating_fix = True
            elif cmd == "thermo" or cmd == "thermo_style":
                has_thermo = True
            elif cmd in ("run", "minimize"):
                has_run_or_minimize = True
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
        if has_box_or_data and not has_atoms and "minimize" not in commands_found:
            errors.append("Simulation box created but no atoms added (missing 'create_atoms', 'read_data', or 'read_restart').")

        # 2. Force field / interaction integrity
        if has_pair_style and not has_pair_coeff and "read_data" not in commands_found:
            errors.append("Defined 'pair_style' but missing corresponding 'pair_coeff' interactions.")
        if not has_pair_style and "read_data" not in commands_found:
            warnings.append("No 'pair_style' defined. System may have zero non-bonded interatomic forces.")

        # 3. Time integration & execution integrity
        if not has_integrating_fix and "minimize" not in commands_found:
            warnings.append("No active time-integrating 'fix' (e.g. 'fix 1 all nve', 'fix 1 all nvt'). Atoms will not move during dynamics.")
        if not has_run_or_minimize:
            warnings.append("Script contains no 'run' or 'minimize' execution directive.")

        # 4. Scientific parameter safety checks
        if not has_timestep and units_style:
            default_dt = 0.001 if units_style == "metal" else (1.0 if units_style == "real" else 0.005)
            assumptions.append(f"Timestep: default {default_dt} ({units_style} units)")

        if units_style == "metal" and timestep_val is not None:
            if timestep_val > 0.003: # > 3 fs in metal ps units
                warnings.append(f"Timestep {timestep_val} ps is high for metal units (> 0.003 ps / 3 fs). Risk of energy drift or lost atoms.")
        elif units_style == "real" and timestep_val is not None:
            if timestep_val > 2.5: # > 2.5 fs
                warnings.append(f"Timestep {timestep_val} fs in real units is dangerously high (> 2.5 fs for flexible bonds/water).")
        elif units_style == "lj" and timestep_val is not None:
            if timestep_val > 0.005:
                warnings.append(f"Timestep {timestep_val} in LJ units exceeds standard stability threshold (0.005 tau).")

        is_valid = len(errors) == 0
        return {
            "valid": is_valid,
            "executable": is_valid,
            "errors": errors,
            "warnings": warnings,
            "assumptions": assumptions,
            "commands": list(set(commands_found))
        }

