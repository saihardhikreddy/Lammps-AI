"""Parameterized Baseline Script Templates for LAMMPS Simulation Workflows."""

def template_lj_fluid(rho: float = 0.8442, temp: float = 1.44, ensemble: str = "NVE", timestep: float = 0.005, nsteps: int = 500, thermo_freq: int = 50) -> str:
    ens_upper = ensemble.upper()
    if ens_upper == "NVT":
        fix_line = f"fix             1 all nvt temp {temp} {temp} 1.0"
    elif ens_upper == "NPT":
        fix_line = f"fix             1 all npt temp {temp} {temp} 1.0 iso 0.0 0.0 1.0"
    else:
        fix_line = "fix             1 all nve"

    return f"""# 3D Lennard-Jones Liquid Simulation
units           lj
atom_style      atomic
boundary        p p p

lattice         fcc {rho}
region          box block 0 6 0 6 0 6
create_box      1 box
create_atoms    1 box
mass            1 1.0

velocity        all create {temp} 87287 loop geom

pair_style      lj/cut 2.5
pair_coeff      1 1 1.0 1.0 2.5

neighbor        0.3 bin
neigh_modify    delay 0 every 20 check no

timestep        {timestep}

{fix_line}

thermo_style    custom step temp pe ke etotal press
thermo          {thermo_freq}
run             {nsteps}
"""

def template_metal_melting(material: str = "Aluminum", element: str = "Al", lattice_a: float = 4.05, mass: float = 26.9815, pot_file: str = "Al_zhou.eam.alloy", ensemble: str = "NVT", timestep: float = 0.001, t_start: float = 300.0, t_stop: float = 1000.0, nsteps: int = 2000, lattice_style: str = "fcc", pair_style: str = "eam/alloy") -> str:
    ens_upper = ensemble.upper()
    if ens_upper == "NPT":
        fix_line = f"fix             1 all npt temp {t_start} {t_stop} 0.1 iso 0.0 0.0 1.0"
    elif ens_upper == "NVE":
        fix_line = "fix             1 all nve"
    else:
        fix_line = f"fix             1 all nvt temp {t_start} {t_stop} 0.1"

    if pair_style == "tersoff":
        pair_lines = f"pair_style      tersoff\npair_coeff      * * {pot_file} {element}"
    else:
        pair_lines = f"pair_style      {pair_style}\npair_coeff      * * {pot_file} {element}"

    return f"""# {material} Crystal Heating and Melting Simulation
units           metal
boundary        p p p
atom_style      atomic

lattice         {lattice_style} {lattice_a}
region          simbox block 0 4 0 4 0 4
create_box      1 simbox
create_atoms    1 box
mass            1 {mass}

velocity        all create {t_start} 4928459 rot yes mom yes dist gaussian

{pair_lines}

neighbor        2.0 bin
neigh_modify    delay 0 every 1 check yes

timestep        {timestep}

thermo_style    custom step temp pe etotal press vol
thermo          50

# Continuous heating from {t_start} K to {t_stop} K ({ens_upper} ensemble)
{fix_line}

run             {nsteps}
"""

def template_uniaxial_tensile(material: str = "Copper", element: str = "Cu", lattice_a: float = 3.615, mass: float = 63.546, pot_file: str = "Cu_zhou.eam.alloy", strain_rate: float = 0.001, temp: float = 300.0, ensemble: str = "NPT", timestep: float = 0.001, eq_steps: int = 1000, run_steps: int = 2000, lattice_style: str = "fcc", pair_style: str = "eam/alloy") -> str:
    if pair_style == "tersoff":
        pair_lines = f"pair_style      tersoff\npair_coeff      * * {pot_file} {element}"
    else:
        pair_lines = f"pair_style      {pair_style}\npair_coeff      * * {pot_file} {element}"

    return f"""# Uniaxial Tensile Loading of {material} Single Crystal
units           metal
boundary        p p p
atom_style      atomic

lattice         {lattice_style} {lattice_a}
region          box block 0 4 0 4 0 8
create_box      1 box
create_atoms    1 box
mass            1 {mass}

{pair_lines}

neighbor        2.0 bin
neigh_modify    delay 0 every 1 check yes

velocity        all create {temp} 12345 mom yes rot yes dist gaussian
timestep        {timestep}

# Stage 1: NPT Equilibration at {temp} K and 0 bar
fix             1 all npt temp {temp} {temp} 0.1 iso 0.0 0.0 1.0
thermo          50
run             {eq_steps}
unfix           1

# Stage 2: Tensile Deformation along Z direction with lateral relaxation
fix             1 all npt temp {temp} {temp} 0.1 x 0.0 0.0 1.0 y 0.0 0.0 1.0
fix             2 all deform 1 z erate {strain_rate} units box remap x

variable        L0 equal lz
variable        strain equal "(lz - v_L0)/v_L0"
variable        stress equal "-pzz/10000.0" # in GPa

thermo_style    custom step temp pzz v_strain v_stress lx ly lz
thermo          50
run             {run_steps}
"""

def template_silicon_thermalization(temp: float = 300.0, ensemble: str = "NPT", timestep: float = 0.001, nsteps: int = 1000) -> str:
    ens_upper = ensemble.upper()
    if ens_upper == "NVT":
        fix_line = f"fix             1 all nvt temp {temp} {temp} 0.1"
    elif ens_upper == "NVE":
        fix_line = "fix             1 all nve"
    else:
        fix_line = f"fix             1 all npt temp {temp} {temp} 0.1 iso 0.0 0.0 1.0"

    return f"""# Silicon Thermalization with 3-Body Tersoff Potential
units           metal
boundary        p p p
atom_style      atomic

lattice         diamond 5.431
region          box block 0 3 0 3 0 3
create_box      1 box
create_atoms    1 box
mass            1 28.0855

pair_style      tersoff
pair_coeff      * * Si.tersoff Si

neighbor        2.0 bin
neigh_modify    delay 0 every 1 check yes

velocity        all create {temp} 528345 mom yes rot yes dist gaussian
timestep        {timestep}

{fix_line}
thermo_style    custom step temp pe etotal press vol
thermo          50
run             {nsteps}
"""

