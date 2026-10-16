"""Parameterized Script Templates for Liquid-State Molecular Dynamics Workflows.

Templates:
- 3D Lennard-Jones model liquid (reduced units)
- Rigid SPC/E liquid water (real units, molecule template, SHAKE, long-range electrostatics)
- Molten metals (metal units, EAM potentials, superheat-melt -> liquid equilibration -> production)

Every template follows the same liquid protocol:
1. Relaxation (energy minimization, or high-temperature melting for crystalline metal starts)
2. Thermostatted equilibration at the target state point
3. Production in the requested ensemble (NVE by default for transport properties)

Every analysis block (RDF, MSD, Green-Kubo) is written so LAMMPS itself reports the
result in the thermo output; nothing is inferred after the fact.
"""
from typing import Optional, Dict, Tuple

# Integrators that thermostat or barostat the system during production.
THERMOSTATTED_ENSEMBLES = {"NVT", "NPT", "LANGEVIN"}

# Green-Kubo unit conversion: eta = convert / (kB * T) * V * s * dt * integral(<P(0)P(t)>).
# Values follow LAMMPS examples/VISCOSITY/in.gk. The final value is reported in:
#   lj    -> reduced units (epsilon * tau / sigma^3)
#   real  -> mPa*s (cP)
#   metal -> mPa*s (cP)
_GK_UNITS: Dict[str, Tuple[float, float, str]] = {
    # units: (convert, kB, label)
    "lj": (1.0, 1.0, "reduced LJ units"),
    # atm->Pa squared * fs->s * A^3->m^3, then Pa*s -> mPa*s (x1000)
    "real": (101325.0 ** 2 * 1.0e-15 * 1.0e-30 * 1.0e3, 1.3806504e-23, "mPa*s"),
    # bar->Pa squared * ps->s * A^3->m^3, then Pa*s -> mPa*s (x1000)
    "metal": ((1.0e5) ** 2 * 1.0e-12 * 1.0e-30 * 1.0e3, 1.3806504e-23, "mPa*s"),
}

# Diffusion coefficient units reported by the MSD slope in each unit system.
MSD_D_UNITS = {"lj": "sigma^2/tau", "real": "A^2/fs", "metal": "A^2/ps"}


def gk_window(units: str) -> Tuple[int, int]:
    """(sample interval s, correlation length p) for the Green-Kubo stress autocorrelation.

    Correlation time covered = s * p * dt: LJ 5 tau, water 2 ps, molten metal 1 ps. These
    exceed the typical decay times of the shear-stress autocorrelation for each system.
    """
    if units == "lj":
        return 5, 200      # 1000 steps * 0.005 tau = 5 tau
    if units == "real":
        return 5, 400      # 2000 steps * 1 fs = 2 ps
    return 5, 200          # 1000 steps * 1 fs = 1 ps (metal)


def production_fix(ensemble: str, temp: float, units: str, pressure_expr: Optional[str] = None) -> str:
    """Integrator line(s) for the production stage, honoring the requested ensemble."""
    ens = ensemble.upper()
    tdamp = {"lj": 0.5, "real": 100.0, "metal": 0.1}[units]
    pdamp = {"lj": 5.0, "real": 1000.0, "metal": 1.0}[units]
    pressure = {"lj": 0.0, "real": 1.0, "metal": 0.0}[units]
    if ens == "NVT":
        return f"fix             prod all nvt temp {temp} {temp} {tdamp}"
    if ens == "NPT":
        p = pressure_expr if pressure_expr is not None else pressure
        return f"fix             prod all npt temp {temp} {temp} {tdamp} iso {p} {p} {pdamp}"
    if ens == "LANGEVIN":
        return (f"fix             prod all nve\n"
                f"fix             prodLgv all langevin {temp} {temp} {tdamp} 48279")
    return "fix             prod all nve"


def _analysis_blocks(units: str, temp: float, compute_rdf: bool, compute_msd: bool,
                     compute_viscosity: bool, rdf_pairs: str, prefix: str) -> Tuple[str, str]:
    """Returns (analysis commands, extra thermo keywords)."""
    blocks = []
    thermo_extra = []

    if compute_rdf:
        blocks.append(f"""# Radial distribution function g(r), time-averaged over production
compute         cRDF all rdf 100 {rdf_pairs}
fix             fRDF all ave/time 100 10 1000 c_cRDF[*] file {prefix}rdf.out mode vector ave running""")

    if compute_msd:
        d_unit = MSD_D_UNITS.get(units, "")
        blocks.append(f"""# Mean squared displacement and Einstein self-diffusion coefficient
# D = slope(MSD vs t) / 6, fitted by LAMMPS over the whole production run [{d_unit}]
compute         cMSD all msd com yes
fix             fMSD all ave/time 10 1 10 c_cMSD[4] file {prefix}msd.out
fix             fMSDvec all vector 10 c_cMSD[4]
variable        D_fit equal slope(f_fMSDvec)/(6.0*10*dt)""")
        thermo_extra.append("c_cMSD[4] v_D_fit")

    if compute_viscosity:
        convert, kb, label = _GK_UNITS[units]
        s, p = gk_window(units)
        blocks.append(f"""# Green-Kubo shear viscosity (after LAMMPS examples/VISCOSITY/in.gk)
# eta = V/(kB*T) * integral <P_ab(0) P_ab(t)> dt, averaged over xy, xz, yz [{label}]
variable        T_gk equal {temp}
variable        pxy equal pxy
variable        pxz equal pxz
variable        pyz equal pyz
fix             fGK all ave/correlate {s} {p} {s * p} v_pxy v_pxz v_pyz type auto file {prefix}gk_acf.out ave running
variable        scale_gk equal {convert:.10e}/({kb:.10e}*v_T_gk)*vol*{s}*dt
variable        eta_xy equal trap(f_fGK[3])*v_scale_gk
variable        eta_xz equal trap(f_fGK[4])*v_scale_gk
variable        eta_yz equal trap(f_fGK[5])*v_scale_gk
variable        eta equal (v_eta_xy+v_eta_xz+v_eta_yz)/3.0""")
        thermo_extra.append("v_eta")

    analysis = ("\n\n" + "\n\n".join(blocks)) if blocks else ""
    return analysis, (" " + " ".join(thermo_extra)) if thermo_extra else ""


def _production_section(units: str, temp: float, ensemble: str, nsteps: int, dump_freq: int,
                        thermo_freq: int, thermo_base: str, compute_rdf: bool, compute_msd: bool,
                        compute_viscosity: bool, rdf_pairs: str, prefix: str,
                        pressure_expr: Optional[str] = None) -> str:
    analysis, thermo_extra = _analysis_blocks(
        units, temp, compute_rdf, compute_msd, compute_viscosity, rdf_pairs, prefix)
    if compute_viscosity:
        # f_fGK can only be read on steps that are multiples of its Nfreq
        s, p = gk_window(units)
        thermo_freq = s * p
    elif compute_msd:
        thermo_freq = max(10, (thermo_freq // 10) * 10)
    return f"""# Stage 3: Production ({ensemble.upper()} ensemble)
reset_timestep  0
compute         atomKE all ke/atom
dump            traj all custom {dump_freq} dump.lammpstrj id type x y z c_atomKE
dump_modify     traj sort id
{production_fix(ensemble, temp, units, pressure_expr)}{analysis}

thermo_style    custom {thermo_base}{thermo_extra}
thermo          {thermo_freq}
run             {nsteps}
undump          traj"""


def template_lj_fluid(
    rho: float = 0.8442,
    temp: float = 1.44,
    ensemble: str = "NVT",
    timestep: float = 0.005,
    nsteps: int = 5000,
    eq_steps: int = 2000,
    thermo_freq: int = 100,
    dump_freq: Optional[int] = None,
    compute_rdf: bool = False,
    compute_msd: bool = False,
    compute_viscosity: bool = False,
    n_cells: int = 6
) -> str:
    """3D Lennard-Jones liquid in reduced units (4 * n_cells^3 atoms)."""
    df = dump_freq if dump_freq else max(10, nsteps // 50)
    is_npt = ensemble.upper() == "NPT"
    eq_steps = max(1000, (eq_steps // 1000) * 1000)
    # NPT production runs at the mean pressure of the NVT equilibration, so it samples the
    # same state point rather than an arbitrary pressure (P* = 0 would boil a T* > 1.3 fluid).
    p_capture = "\nfix             pEq all ave/time 10 100 1000 c_thermo_press" if is_npt else ""
    p_store = "\nvariable        P_eq equal $(f_pEq)\nunfix           pEq" if is_npt else ""
    production = _production_section(
        "lj", temp, ensemble, nsteps, df, thermo_freq, "step temp pe ke etotal press",
        compute_rdf, compute_msd, compute_viscosity, "1 1", "",
        pressure_expr="${P_eq}" if is_npt else None)

    return f"""# 3D Lennard-Jones Liquid ({4 * n_cells ** 3} atoms)
# Units: reduced LJ units (sigma = 1, epsilon = 1, m = 1)
units           lj
atom_style      atomic
boundary        p p p

lattice         fcc {rho}
region          box block 0 {n_cells} 0 {n_cells} 0 {n_cells}
create_box      1 box
create_atoms    1 box
mass            1 1.0

pair_style      lj/cut 2.5
pair_coeff      1 1 1.0 1.0 2.5

neighbor        0.3 bin
neigh_modify    delay 0 every 1 check yes

timestep        {timestep}

# Stage 1: Energy minimization
minimize        1.0e-4 1.0e-6 100 1000
reset_timestep  0

# Stage 2: NVT equilibration at T* = {temp} (the fcc start melts at this state point)
velocity        all create {temp} 87287 loop geom mom yes rot yes dist gaussian
fix             eq all nvt temp {temp} {temp} 0.5{p_capture}
thermo_style    custom step temp pe ke etotal press
thermo          {thermo_freq}
run             {eq_steps}{p_store}
unfix           eq

{production}
"""


# SPC/E water molecule template (Berendsen, Grigera & Straatsma, J. Phys. Chem. 1987, 91, 6269).
# O at the origin, r(OH) = 1.0 A, angle(HOH) = 109.47 deg; q_O = -0.8476 e, q_H = +0.4238 e.
SPCE_MOLECULE_FILE = """SPC/E water molecule (Berendsen et al. 1987)

3 atoms
2 bonds
1 angles

Coords

1    0.000000   0.000000   0.000000
2    1.000000   0.000000   0.000000
3   -0.333807   0.942641   0.000000

Types

1    1
2    2
3    2

Charges

1   -0.8476
2    0.4238
3    0.4238

Bonds

1    1    1    2
2    1    1    3

Angles

1    1    2    1    3
"""


def template_water_liquid(
    temp: float = 300.0,
    ensemble: str = "NVT",
    timestep: float = 1.0,
    nsteps: int = 5000,
    eq_steps: int = 5000,
    kspace_choice: str = "pppm",
    dump_freq: Optional[int] = None,
    thermo_freq: int = 100,
    compute_rdf: bool = False,
    compute_msd: bool = False,
    compute_viscosity: bool = False,
    n_cells: int = 6
) -> str:
    """Rigid SPC/E water: n_cells^3 molecules on a simple-cubic grid at 1.0 g/cm^3.

    Each molecule is placed from a molecule template (so it carries its charges, bonds
    and angle), randomly oriented, then relaxed, constrained with SHAKE and equilibrated.
    """
    df = dump_freq if dump_freq else max(10, nsteps // 50)
    n_mol = n_cells ** 3
    # 1 molecule per sc cell at 0.997 g/cm^3 -> 29.9 A^3 per molecule -> a = 3.1034 A
    spacing = 3.1034

    if kspace_choice == "cut":
        elec = """pair_style      lj/cut/coul/cut 9.8
# ELECTROSTATICS WARNING: the installed LAMMPS lacks the KSPACE package, so Coulomb
# interactions are truncated at 9.8 A. SPC/E was parameterized with Ewald summation;
# truncation distorts the dielectric response, structure and dynamics of water."""
        kspace_line = ""
    elif kspace_choice == "ewald":
        elec = "pair_style      lj/cut/coul/long 9.8\n# Long-range electrostatics: Ewald summation"
        kspace_line = "kspace_style    ewald 1.0e-4"
    else:
        elec = "pair_style      lj/cut/coul/long 9.8\n# Long-range electrostatics: PPPM (particle-particle particle-mesh)"
        kspace_line = "kspace_style    pppm 1.0e-4"

    production = _production_section(
        "real", temp, ensemble, nsteps, df, thermo_freq,
        "step temp pe etotal press density",
        compute_rdf, compute_msd, compute_viscosity, "1 1 1 2", "water_")

    # One print per line: LAMMPS drops blank lines inside triple-quoted strings, but the
    # molecule-file format requires a blank line after every section header.
    mol_lines = SPCE_MOLECULE_FILE.rstrip().splitlines()
    mol_print = "\n".join(
        f'print           "{line}" {"file" if k == 0 else "append"} spce.mol screen no'
        for k, line in enumerate(mol_lines)
    )

    return f"""# Rigid SPC/E Liquid Water ({n_mol} molecules, {3 * n_mol} atoms)
# Parameters: Berendsen, Grigera & Straatsma, J. Phys. Chem. 1987, 91, 6269-6271
# O: q = -0.8476 e, eps = 0.1553 kcal/mol, sigma = 3.166 A;  H: q = +0.4238 e, no LJ
# Geometry: r(OH) = 1.0 A, angle(HOH) = 109.47 deg, held rigid by SHAKE

units           real
atom_style      full
boundary        p p p

# Write the SPC/E molecule template next to this input (relative path, inside the run folder)
{mol_print}

# Simple-cubic grid, one randomly oriented molecule per site (density 1.0 g/cm^3)
lattice         sc {spacing}
region          box block 0 {n_cells} 0 {n_cells} 0 {n_cells}
create_box      2 box bond/types 1 angle/types 1 extra/bond/per/atom 2 extra/angle/per/atom 1 extra/special/per/atom 2
molecule        h2o spce.mol
create_atoms    0 box mol h2o 45585

mass            1 15.9994
mass            2 1.008

{elec}
pair_coeff      1 1 0.1553 3.166
pair_coeff      1 2 0.0 1.0
pair_coeff      2 2 0.0 1.0
{kspace_line}

bond_style      harmonic
bond_coeff      1 1000.0 1.0
angle_style     harmonic
angle_coeff     1 100.0 109.47

neighbor        2.0 bin
neigh_modify    delay 0 every 1 check yes

# Stage 1: Energy minimization (flexible, before the SHAKE constraints are switched on)
thermo_style    custom step temp pe etotal press density
thermo          {thermo_freq}
minimize        1.0e-4 1.0e-6 200 2000
reset_timestep  0

# Rigid geometry via SHAKE (fix ID group-ID shake tol iter N b bond-types a angle-types)
fix             rigidH2O all shake 0.0001 20 0 b 1 a 1

timestep        {timestep}

# Stage 2: NVT equilibration (Nose-Hoover, Tdamp = 100 fs)
velocity        all create {temp} 4928459 mom yes rot yes dist gaussian
fix             eq all nvt temp {temp} {temp} 100.0
run             {eq_steps}
unfix           eq

{production}
"""


def template_molten_metal(
    material: str = "Aluminum",
    element: str = "Al",
    lattice_a: float = 4.05,
    mass: float = 26.9815,
    pot_file: str = "Al_zhou.eam.alloy",
    ensemble: str = "NVT",
    timestep: float = 0.001,
    t_start: float = 300.0,
    t_stop: float = 1100.0,
    t_melt: float = 933.47,
    nsteps: int = 5000,
    eq_steps: int = 5000,
    lattice_style: str = "fcc",
    pair_style: str = "eam/alloy",
    dump_freq: Optional[int] = None,
    thermo_freq: int = 100,
    compute_rdf: bool = False,
    compute_msd: bool = False,
    compute_viscosity: bool = False,
    n_cells: int = 5
) -> str:
    """Molten metal: melt the crystal well above T_m, bring the liquid to t_stop, then produce.

    A defect-free periodic crystal superheats well past its thermodynamic melting point
    before it melts homogeneously, so the melt stage runs at T_hot = max(1.5 T_m, t_stop + 300 K).
    """
    df = dump_freq if dump_freq else max(10, nsteps // 50)
    t_hot = round(max(1.5 * t_melt, t_stop + 300.0), 1)
    heat_steps = max(1000, eq_steps // 2)

    if pair_style == "eam":
        # DYNAMO funcfl files (e.g. Ni_u3.eam) take one file per type pair and no element list
        pair_lines = f"pair_style      eam\npair_coeff      1 1 {pot_file}"
    else:
        pair_lines = f"pair_style      {pair_style}\npair_coeff      * * {pot_file} {element}"

    atoms_per_cell = 4 if lattice_style == "fcc" else 2
    n_atoms = atoms_per_cell * n_cells ** 3

    production = _production_section(
        "metal", t_stop, ensemble, nsteps, df, thermo_freq,
        "step temp pe etotal press vol",
        compute_rdf, compute_msd, compute_viscosity, "1 1", "molten_")

    return f"""# Molten {material} ({n_atoms} atoms): superheat melt -> liquid equilibration -> production
units           metal
boundary        p p p
atom_style      atomic

lattice         {lattice_style} {lattice_a}
region          box block 0 {n_cells} 0 {n_cells} 0 {n_cells}
create_box      1 box
create_atoms    1 box
mass            1 {mass}

{pair_lines}

neighbor        2.0 bin
neigh_modify    delay 0 every 1 check yes

timestep        {timestep}
thermo_style    custom step temp pe etotal press vol
thermo          {thermo_freq}

velocity        all create {t_start} 4928459 rot yes mom yes dist gaussian

# Stage 1a: Heat the crystal at zero pressure to T_hot = {t_hot} K (T_m = {t_melt} K)
fix             melt all npt temp {t_start} {t_hot} 0.1 iso 0.0 0.0 1.0
run             {heat_steps}
unfix           melt

# Stage 1b: Hold at T_hot so the superheated crystal melts completely
fix             melt all npt temp {t_hot} {t_hot} 0.1 iso 0.0 0.0 1.0
run             {eq_steps}
unfix           melt

# Stage 2: Cool the liquid to {t_stop} K and equilibrate at zero pressure
fix             eq all npt temp {t_hot} {t_stop} 0.1 iso 0.0 0.0 1.0
run             {heat_steps}
unfix           eq
fix             eq all npt temp {t_stop} {t_stop} 0.1 iso 0.0 0.0 1.0
run             {eq_steps}
unfix           eq

{production}
"""


# Alias for backwards compatibility
template_metal_melting = template_molten_metal
