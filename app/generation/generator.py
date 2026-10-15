"""Documentation-Grounded LAMMPS Input Script Generator for Liquid-State MD.

Supported systems:
- Lennard-Jones model fluid / liquid argon (reduced units)
- Rigid SPC/E liquid water
- Molten metals (Al, Cu, Ni, Fe) with EAM potentials

Guarantees:
- Every parameter the user states (ensemble, temperature, timestep, atom count, dump and
  thermo intervals) is either used in the script or reported as overridden, with the reason.
- Transport properties (diffusion, viscosity) default to NVE production; a thermostatted
  production run is only generated when explicitly requested, and then flagged.
- Solid mechanics (tensile deformation) is refused as out of scope.
"""
from typing import Dict, Any, List, Optional
from app.knowledge.retriever import LocalKnowledgeRetriever
from app.generation.templates import (
    template_lj_fluid,
    template_water_liquid,
    template_molten_metal,
    THERMOSTATTED_ENSEMBLES,
    MSD_D_UNITS,
    gk_window,
)
from app.generation.planner import SimulationPlanner
from app.lammps.detector import detect_lammps

SUPPORTED_ENSEMBLES = {"NVE", "NVT", "NPT", "LANGEVIN"}

# Production-run length (steps) by system and analysis. Long enough for the analysis to be
# meaningful, short enough to finish within the local execution timeout on a laptop.
PRODUCTION_STEPS = {
    "lj":    {"default": 5000, "diffusion": 20000, "viscosity": 50000},
    "water": {"default": 5000, "diffusion": 20000, "viscosity": 20000},
    "metal": {"default": 5000, "diffusion": 10000, "viscosity": 20000},
}

# LJ time unit for argon (sigma = 3.405 A, epsilon/kB = 119.8 K, m = 39.948 u): tau = 2.156 ps
ARGON_TAU_PS = 2.156
ARGON_EPS_K = 119.8


def _cells_for_atoms(atom_count: Optional[int], atoms_per_cell: int, default: int) -> int:
    """Lattice repetitions giving approximately atom_count atoms."""
    if not atom_count or atom_count <= 0:
        return default
    n = round((atom_count / atoms_per_cell) ** (1.0 / 3.0))
    return max(2, min(n, 40))


class ScriptGenerator:
    """Generates complete, physically sound LAMMPS liquid-state input scripts."""

    def __init__(self, retriever: LocalKnowledgeRetriever):
        self.retriever = retriever
        self.planner = SimulationPlanner()

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _convert_timestep(dt: Optional[float], unit: Optional[str], units: str,
                          default: float, notes: List[str], is_argon: bool = False) -> float:
        """Convert a user timestep to the template's unit system, reporting what was done."""
        native = {"real": "fs", "metal": "ps", "lj": "tau"}[units]
        if dt is None:
            return default
        if unit is None or unit == native:
            if unit is None:
                notes.append(f"Timestep: {dt} interpreted in native '{units}' units ({native}); "
                             f"state 'fs' or 'ps' explicitly to avoid ambiguity.")
            return dt
        if units == "real":
            return dt * 1000.0 if unit == "ps" else dt
        if units == "metal":
            return dt / 1000.0 if unit == "fs" else dt
        # lj units
        if is_argon and unit in ("fs", "ps"):
            dt_ps = dt / 1000.0 if unit == "fs" else dt
            converted = round(dt_ps / ARGON_TAU_PS, 6)
            notes.append(f"Timestep: {dt} {unit} converted to {converted} tau using argon tau = {ARGON_TAU_PS} ps.")
            return converted
        notes.append(f"Timestep: requested {dt} {unit} has no meaning in reduced LJ units; "
                     f"using the default {default} tau instead.")
        return default

    def _kspace_choice(self, notes: List[str]) -> str:
        detection = detect_lammps()
        packages = {p.upper() for p in detection.get("packages", [])}
        if not detection.get("detected"):
            notes.append("Electrostatics: PPPM assumed (no LAMMPS binary detected to confirm the KSPACE package).")
            return "pppm"
        missing = [p for p in ("MOLECULE", "RIGID") if packages and p not in packages]
        if missing:
            notes.append(f"Package warning: the detected LAMMPS build lacks {', '.join(missing)}, "
                         f"which this water model needs (atom_style full / fix shake).")
        if not packages or "KSPACE" in packages:
            return "pppm"
        notes.append("Electrostatics WARNING: detected LAMMPS has no KSPACE package, so Coulomb "
                     "interactions are truncated at 9.8 A (lj/cut/coul/cut). SPC/E assumes Ewald "
                     "summation; structure, dielectric and transport results will be biased.")
        return "cut"

    # ── main entry point ────────────────────────────────────────────────────
    def generate(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        mat_info = spec.get("material_info")
        raw_mat_name = spec.get("material_name") or "Lennard-Jones Liquid"
        mat_name = mat_info.get("name", raw_mat_name.title()) if mat_info else raw_mat_name.title()
        sim_type = (spec.get("simulation_type") or "equilibration").lower()
        requested_ens = (spec.get("ensemble") or "NVT").upper()
        ens_specified = bool(spec.get("ensemble_specified", False))
        temp = spec.get("temperature") if spec.get("temperature") is not None else 300.0
        dt = spec.get("timestep")
        dt_unit = spec.get("timestep_unit")
        atom_count = spec.get("atom_count")
        dump_interval = spec.get("dump_interval")
        thermo_interval = spec.get("thermo_interval")

        # ── 1. Out-of-scope solid mechanics ────────────────────────────────
        if sim_type == "unsupported_tensile":
            plan = self.planner.create_plan(spec)
            return {
                "goal": "Unsupported: Solid-State Mechanics Out of Scope",
                "script": (
                    "# OUT OF SCOPE:\n"
                    "# Tensile deformation, strain loading, and solid mechanics are out of scope for this\n"
                    "# liquid-state research assistant. Request a liquid simulation instead (LJ fluid,\n"
                    "# SPC/E water, molten metal, RDF, Green-Kubo viscosity, or self-diffusion)."
                ),
                "plan": plan,
                "assumptions": [
                    "Scope constraint: solid mechanics and tensile deformation are not supported.",
                ],
                "required_files": [],
                "citations": [],
                "run_command": "",
                "limitations": "Solid mechanics has no liquid analogue in this tool.",
            }

        # ── 2. Analyses requested ──────────────────────────────────────────
        compute_rdf = "rdf" in sim_type or "structure" in sim_type
        compute_msd = "diffusion" in sim_type
        compute_viscosity = "viscosity" in sim_type
        transport = compute_msd or compute_viscosity

        notes: List[str] = []

        # ── 3. Production ensemble (ensemble honesty) ──────────────────────
        prod_ens = requested_ens if requested_ens in SUPPORTED_ENSEMBLES else "NVT"
        if requested_ens not in SUPPORTED_ENSEMBLES:
            notes.append(f"Ensemble: '{requested_ens}' is not supported; using NVT.")
        if transport and not ens_specified:
            prod_ens = "NVE"
            notes.append("Production ensemble: NVE (default for transport properties, because a "
                         "thermostat perturbs the particle dynamics being measured). "
                         "Equilibration is still done under NVT.")
        elif transport and prod_ens in THERMOSTATTED_ENSEMBLES:
            notes.append(f"Transport WARNING: production runs in {prod_ens} as requested. Thermostat/"
                         f"barostat coupling perturbs the dynamics, so D and viscosity from this run are "
                         f"biased; NVE production is the standard choice.")

        if sim_type == "quench":
            notes.append("Quench/cooling protocols are not implemented; generated a liquid "
                         "equilibration at the final temperature instead. The quench rate and start "
                         "temperature were not used.")

        kind = "default"
        if compute_viscosity:
            kind = "viscosity"
        elif compute_msd:
            kind = "diffusion"

        phase_warnings: List[str] = []
        required_files: List[str] = []

        mat_lower = mat_name.lower()
        is_water = mat_lower in ("water", "h2o", "spc/e", "spce")
        is_metal = bool(mat_info and mat_info.get("category") == "molten_metal")

        # ── 4a. SPC/E water ────────────────────────────────────────────────
        if is_water:
            units = "real"
            nsteps = PRODUCTION_STEPS["water"][kind]
            timestep_val = self._convert_timestep(dt, dt_unit, "real", 1.0, notes)
            if temp < 273.15:
                phase_warnings.append(
                    f"Phase Warning: {temp} K is below the freezing point of water (273.15 K at 1 atm). "
                    f"SPC/E water at this temperature is supercooled (its own melting point is ~215 K), "
                    f"not the stable liquid.")
            n_cells = _cells_for_atoms(atom_count // 3 if atom_count else None, 1, 6)
            kspace_choice = self._kspace_choice(notes)
            df = dump_interval or max(10, nsteps // 50)
            script = template_water_liquid(
                temp=temp, ensemble=prod_ens, timestep=timestep_val, nsteps=nsteps,
                eq_steps=5000, kspace_choice=kspace_choice, dump_freq=df,
                thermo_freq=thermo_interval or 100, compute_rdf=compute_rdf,
                compute_msd=compute_msd, compute_viscosity=compute_viscosity, n_cells=n_cells)
            n_atoms = 3 * n_cells ** 3
            box = round(n_cells * 3.1034, 2)
            visual_metadata = {
                "system": "SPC/E Water",
                "types": {"1": {"name": "O", "color": "#ff4444", "radius": 1.52},
                          "2": {"name": "H", "color": "#ffffff", "radius": 1.10}},
                "box_size": [box, box, box],
            }
            elec = {"pppm": "PPPM long-range (kspace_style pppm 1e-4)",
                    "ewald": "Ewald long-range (kspace_style ewald 1e-4)",
                    "cut": "TRUNCATED Coulomb at 9.8 A (no KSPACE package)"}[kspace_choice]
            assumptions = [
                f"System: {n_cells ** 3} rigid SPC/E water molecules ({n_atoms} atoms) at 1.0 g/cm^3",
                "Units: real (A, kcal/mol, fs, K, atm)",
                "Model: q_O = -0.8476 e, q_H = +0.4238 e, r(OH) = 1.0 A, angle(HOH) = 109.47 deg (SHAKE)",
                f"Electrostatics: {elec}, real-space cutoff 9.8 A",
                f"Protocol: minimization -> NVT equilibration (5000 steps) -> {prod_ens} production ({nsteps} steps)",
                f"Timestep: {timestep_val} fs",
            ]
            citations = [
                "Berendsen, Grigera & Straatsma, J. Phys. Chem. 91, 6269 (1987) - SPC/E model",
                "LAMMPS Manual -> molecule, create_atoms, fix shake",
                "LAMMPS Manual -> pair_style lj/cut/coul/long, kspace_style",
            ]

        # ── 4b. Molten metals ──────────────────────────────────────────────
        elif is_metal:
            units = "metal"
            nsteps = PRODUCTION_STEPS["metal"][kind]
            elem = mat_info["element"]
            display_name = mat_info.get("name", mat_name)
            t_melt = mat_info.get("t_melt", 1000.0)
            pot = mat_info.get("pot_file", f"{elem}_zhou.eam.alloy")
            lat_style = mat_info.get("lattice", "fcc")
            p_style = mat_info.get("potential", "eam/alloy")
            if temp < t_melt:
                liquid_target = round(t_melt + 100.0, 2)
                phase_warnings.append(
                    f"Phase Warning: {temp} K is below the experimental melting point of {display_name} "
                    f"({t_melt} K), where it is a crystalline solid. The liquid is simulated at "
                    f"{liquid_target} K instead of the requested {temp} K.")
            else:
                liquid_target = temp
            timestep_val = self._convert_timestep(dt, dt_unit, "metal", 0.001, notes)
            atoms_per_cell = 4 if lat_style == "fcc" else 2
            n_cells = _cells_for_atoms(atom_count, atoms_per_cell, 5 if lat_style == "fcc" else 6)
            n_atoms = atoms_per_cell * n_cells ** 3
            t_hot = round(max(1.5 * t_melt, liquid_target + 300.0), 1)
            df = dump_interval or max(10, nsteps // 50)
            script = template_molten_metal(
                material=display_name, element=elem, lattice_a=mat_info.get("a", 4.05),
                mass=mat_info.get("mass", 26.9815), pot_file=pot, ensemble=prod_ens,
                timestep=timestep_val, t_start=300.0, t_stop=liquid_target, t_melt=t_melt,
                nsteps=nsteps, eq_steps=5000, lattice_style=lat_style, pair_style=p_style,
                dump_freq=df, thermo_freq=thermo_interval or 100, compute_rdf=compute_rdf,
                compute_msd=compute_msd, compute_viscosity=compute_viscosity, n_cells=n_cells)
            a = mat_info.get("a", 4.05)
            visual_metadata = {
                "system": f"Molten {display_name}",
                "types": {"1": {"name": elem, "color": "#00f0ff", "radius": 1.43}},
                "box_size": [round(n_cells * a, 2)] * 3,
            }
            assumptions = [
                f"System: {n_atoms} {display_name} atoms, starting from a {lat_style} crystal",
                "Units: metal (A, eV, ps, K, bar)",
                f"Potential: {p_style} ({pot})",
                f"Protocol: heat at zero pressure to {t_hot} K and hold (a periodic crystal superheats "
                f"past T_m before melting) -> cool to {liquid_target} K and equilibrate (NPT, 0 bar) "
                f"-> {prod_ens} production ({nsteps} steps)",
                "Check: confirm the liquid state from the output - the MSD must keep growing linearly "
                "and g(r) must show no crystalline peaks. The potential's own melting point can differ "
                "from experiment.",
                f"Timestep: {timestep_val} ps ({round(timestep_val * 1000, 4)} fs)",
            ]
            citations = [
                "LAMMPS Manual -> units metal",
                f"LAMMPS Manual -> pair_style {p_style}",
                "LAMMPS Manual -> fix nvt/npt (Nose-Hoover)",
            ]
            required_files = [f"{pot} (from the LAMMPS potentials directory)"]

        # ── 4c. Lennard-Jones fluid / argon ────────────────────────────────
        else:
            units = "lj"
            nsteps = PRODUCTION_STEPS["lj"][kind]
            is_argon = mat_lower in ("argon", "ar")
            if is_argon:
                if temp >= 10.0:
                    target_t = round(temp / ARGON_EPS_K, 3)
                    notes.append(f"Argon mapped to reduced LJ units: T* = {temp} K / {ARGON_EPS_K} K = {target_t}; "
                                 f"lengths in sigma = 3.405 A, time in tau = {ARGON_TAU_PS} ps.")
                else:
                    target_t = temp
                if temp < 83.8 and temp >= 10.0:
                    phase_warnings.append(
                        f"Phase Warning: {temp} K is below the triple point of argon (83.8 K); "
                        f"argon is a solid there.")
            else:
                if temp < 10.0:
                    target_t = temp
                else:
                    target_t = 1.44
                    if spec.get("user_temperature_specified"):
                        notes.append(f"Temperature: {temp} cannot be used in reduced LJ units; used T* = 1.44. "
                                     f"Give a reduced temperature (e.g. T* = 1.0) or ask for argon in kelvin.")
            if target_t < 0.69:
                phase_warnings.append(
                    f"Phase Warning: T* = {target_t} is below the LJ triple point (T* ~ 0.69); "
                    f"the fluid will crystallize at rho* = 0.8442.")
            timestep_val = self._convert_timestep(dt, dt_unit, "lj", 0.005, notes, is_argon=is_argon)
            n_cells = _cells_for_atoms(atom_count, 4, 6)
            n_atoms = 4 * n_cells ** 3
            df = dump_interval or max(10, nsteps // 50)
            script = template_lj_fluid(
                rho=0.8442, temp=target_t, ensemble=prod_ens, timestep=timestep_val,
                nsteps=nsteps, eq_steps=2000, thermo_freq=thermo_interval or 100, dump_freq=df,
                compute_rdf=compute_rdf, compute_msd=compute_msd,
                compute_viscosity=compute_viscosity, n_cells=n_cells)
            box = round(n_cells * (4 / 0.8442) ** (1 / 3), 2)
            visual_metadata = {
                "system": f"LJ Fluid ({mat_name})",
                "types": {"1": {"name": "Ar" if is_argon else "LJ", "color": "#a855f7", "radius": 0.5}},
                "box_size": [box, box, box],
            }
            assumptions = [
                f"System: {n_atoms} Lennard-Jones particles ({mat_name}) at rho* = 0.8442",
                "Units: lj (sigma = epsilon = m = 1)",
                "Potential: 12-6 Lennard-Jones, cutoff 2.5 sigma",
                f"Protocol: minimization -> NVT equilibration at T* = {target_t} -> {prod_ens} production ({nsteps} steps)",
                f"Timestep: {timestep_val} tau",
            ]
            if prod_ens == "NPT":
                assumptions.append("NPT production pressure: the mean pressure of the NVT equilibration.")
            citations = [
                "LAMMPS Manual -> units lj, pair_style lj/cut",
                "LAMMPS examples/melt/in.melt",
            ]

        # ── 5. Analysis notes ──────────────────────────────────────────────
        if atom_count:
            notes.append(f"Atom count: requested ~{atom_count}, generated {n_atoms} (nearest complete lattice).")
            if n_atoms > 20000:
                notes.append("Size warning: more than 20,000 atoms may exceed the local execution timeout.")
        if compute_msd:
            notes.append(f"Diffusion: LAMMPS reports D = slope(MSD)/6 as v_D_fit in {MSD_D_UNITS[units]} "
                         f"(fitted over the whole production run, including the short ballistic regime).")
        if compute_viscosity:
            s, p = gk_window(units)
            label = {"lj": "reduced LJ units", "real": "mPa*s", "metal": "mPa*s"}[units]
            notes.append(f"Viscosity: LAMMPS reports the Green-Kubo estimate as v_eta in {label} "
                         f"(stress autocorrelation over {s * p} steps). A single {nsteps}-step run gives a "
                         f"rough estimate only; converge it with longer runs and several independent seeds.")
        if compute_rdf:
            notes.append("Structure: g(r) is time-averaged over production and written to the rdf output file.")

        assumptions.extend(phase_warnings)
        assumptions.extend(notes)

        plan_spec = dict(spec)
        plan_spec["ensemble"] = prod_ens
        plan = self.planner.create_plan(plan_spec)

        return {
            "goal": f"Simulate liquid {mat_name} ({sim_type}) with {prod_ens} production",
            "script": script,
            "plan": plan,
            "assumptions": assumptions,
            "production_ensemble": prod_ens,
            "visual_metadata": visual_metadata,
            "required_files": required_files,
            "citations": citations,
            "run_command": "lmp -in in.run",
            "limitations": "Classical empirical potentials: no electronic structure, polarization, or bond breaking.",
        }
