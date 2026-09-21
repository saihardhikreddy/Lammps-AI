"""Built-in authoritative LAMMPS documentation chunks, command references, and validated example scripts."""
from app.knowledge.schema import DocChunk, ExampleChunk

BUILTIN_COMMANDS = {
    "units": {
        "syntax": "units style",
        "styles": ["lj", "real", "metal", "si", "cgs", "electron", "micro", "nano"],
        "section": "General Commands",
        "description": "Sets the style of units used for a simulation. Must be used before simulation box is defined.",
        "details": "metal: energy=eV, distance=Angstroms, time=picoseconds, mass=grams/mole. lj: all quantities unitless / reduced.",
        "keywords": ["units", "unit system", "metal", "real", "lj", "picoseconds", "eV", "angstroms"]
    },
    "atom_style": {
        "syntax": "atom_style style args",
        "styles": ["atomic", "charge", "full", "molecular", "bond", "angle", "sphere"],
        "section": "General Commands",
        "description": "Defines what style of atoms to use in a simulation, determining per-atom data fields.",
        "details": "atomic: coarse-grain / metal without charges. full: molecular mechanics with bonds, angles, dihedrals, impropers, and partial charges.",
        "keywords": ["atom_style", "atomic", "charge", "full", "molecular", "bonds"]
    },
    "boundary": {
        "syntax": "boundary x y z",
        "styles": ["p", "f", "s", "m"],
        "section": "General Commands",
        "description": "Sets the boundary conditions for the 3 dimensions of the simulation box.",
        "details": "p = periodic, f = fixed / non-periodic, s = shrink-wrapped, m = shrink-wrapped with minimum value.",
        "keywords": ["boundary", "periodic boundary conditions", "pbc", "p p p", "shrink-wrapped", "fixed boundary"]
    },
    "dimension": {
        "syntax": "dimension N",
        "styles": ["2", "3"],
        "section": "General Commands",
        "description": "Set the dimensionality of the simulation. Default is 3.",
        "details": "Must be specified before simulation box is created.",
        "keywords": ["dimension", "2D", "3D", "dimensionality"]
    },
    "lattice": {
        "syntax": "lattice style scale args",
        "styles": ["none", "sc", "bcc", "fcc", "hcp", "diamond", "sq", "sq2", "hex", "custom"],
        "section": "Lattice & Geometry",
        "description": "Defines a lattice for creating atoms and regions.",
        "details": "fcc: Face-Centered Cubic with 4 basis atoms. bcc: Body-Centered Cubic with 2 basis atoms. scale: lattice constant in distance units.",
        "keywords": ["lattice", "fcc", "bcc", "hcp", "diamond", "lattice constant", "spacing"]
    },
    "region": {
        "syntax": "region ID style args keyword arg ...",
        "styles": ["block", "sphere", "cylinder", "cone", "plane", "prism", "union", "intersect"],
        "section": "Lattice & Geometry",
        "description": "Defines a geometric region of space for creating atoms, boxes, or groups.",
        "details": "block: xlo xhi ylo yhi zlo zhi. Coordinates are in lattice or box units depending on units keyword.",
        "keywords": ["region", "block", "sphere", "cylinder", "simulation box", "geometry"]
    },
    "create_box": {
        "syntax": "create_box N region-ID keyword value ...",
        "styles": [],
        "section": "Setup Commands",
        "description": "Creates a simulation box with N atom types based on the specified region.",
        "details": "Must be invoked after region is defined and before atoms are created or placed.",
        "keywords": ["create_box", "simulation box", "atom types", "box region"]
    },
    "create_atoms": {
        "syntax": "create_atoms type style args ...",
        "styles": ["box", "region", "single", "random"],
        "section": "Setup Commands",
        "description": "Creates atoms on a lattice inside the simulation box or within a region.",
        "details": "create_atoms 1 box places type 1 atoms on all lattice sites within the entire simulation box.",
        "keywords": ["create_atoms", "populate atoms", "lattice placement", "box", "region"]
    },
    "mass": {
        "syntax": "mass type-ID value",
        "styles": [],
        "section": "Setup Commands",
        "description": "Sets the mass for all atoms of a specific atom type.",
        "details": "Units depend on units style (grams/mole for metal and real, 1.0 for lj).",
        "keywords": ["mass", "atomic mass", "molecular weight", "grams/mole"]
    },
    "pair_style": {
        "syntax": "pair_style style args",
        "styles": ["lj/cut", "eam", "eam/alloy", "eam/fs", "tersoff", "sw", "meam", "airebo", "reaxff", "buck", "morse", "dpd"],
        "section": "Force Field Commands",
        "description": "Sets the interatomic potential model used to compute pairwise and multi-body interactions.",
        "details": "lj/cut: 12-6 Lennard-Jones with spherical cutoff. eam/alloy: Embedded Atom Method for multi-element metallic systems.",
        "keywords": ["pair_style", "potential", "force field", "lj/cut", "eam/alloy", "tersoff", "sw", "interatomic potential"]
    },
    "pair_coeff": {
        "syntax": "pair_coeff I J args",
        "styles": [],
        "section": "Force Field Commands",
        "description": "Specifies force field parameters or potential file paths for atom type pairs I and J.",
        "details": "For eam/alloy: pair_coeff * * pot_file.eam.alloy Element1 Element2. For lj/cut: pair_coeff 1 1 epsilon sigma [cutoff].",
        "keywords": ["pair_coeff", "potential parameters", "epsilon", "sigma", "cutoff", "potential file"]
    },
    "velocity": {
        "syntax": "velocity group-ID style args ...",
        "styles": ["create", "set", "scale", "ramp", "zero"],
        "section": "Kinetic & State",
        "description": "Initializes or manipulates atomic velocities for a group of atoms.",
        "details": "velocity all create 300.0 87287 dist gaussian initializes a Maxwell-Boltzmann thermal distribution at 300 K.",
        "keywords": ["velocity", "velocity create", "temperature initialization", "thermalization", "maxwell-boltzmann"]
    },
    "fix": {
        "syntax": "fix ID group-ID style args ...",
        "styles": ["nvt", "npt", "nve", "langevin", "box/relax", "deform", "recenter", "ave/time", "ave/spatial"],
        "section": "Time Integration & Ensembles",
        "description": "Applies boundary constraints, thermodynamic ensembles, time integration, or external forces.",
        "details": "fix 1 all nvt temp 300 300 0.1 couples the system to a Nose-Hoover thermostat with temperature damping time Tdamp.",
        "keywords": ["fix", "nvt", "npt", "nve", "thermostat", "barostat", "nose-hoover", "time integration", "ensemble"]
    },
    "unfix": {
        "syntax": "unfix fix-ID",
        "styles": [],
        "section": "Time Integration & Ensembles",
        "description": "Deletes a previously defined fix command.",
        "details": "Allows switching between equilibration and production ensembles during multi-stage simulations.",
        "keywords": ["unfix", "remove fix", "switch ensemble"]
    },
    "compute": {
        "syntax": "compute ID group-ID style args ...",
        "styles": ["temp", "pe", "ke", "pressure", "rdf", "msd", "vacf", "stress/atom", "pe/atom"],
        "section": "Analysis & Computes",
        "description": "Defines a computation to be performed on atomic properties, thermodynamic states, or structural metrics.",
        "details": "compute 1 all rdf 100 1 1 calculates the pair radial distribution function g(r). compute 2 all msd calculates Mean Squared Displacement.",
        "keywords": ["compute", "compute rdf", "compute msd", "radial distribution function", "mean squared displacement", "stress/atom"]
    },
    "thermo": {
        "syntax": "thermo N",
        "styles": [],
        "section": "Output Commands",
        "description": "Prints thermodynamic output to screen and log file every N timesteps.",
        "details": "thermo 100 prints thermodynamics every 100 timesteps.",
        "keywords": ["thermo", "thermodynamic output", "screen output", "frequency"]
    },
    "thermo_style": {
        "syntax": "thermo_style style args",
        "styles": ["one", "multi", "custom"],
        "section": "Output Commands",
        "description": "Specifies the contents and format of thermodynamic output printed during the run.",
        "details": "Custom keywords include: step, temp, epair, emol, pe, ke, etotal, press, vol, density, lx, ly, lz, pxx, pyy, pzz.",
        "keywords": ["thermo_style", "custom", "step", "temp", "pe", "ke", "etotal", "press", "vol", "density"]
    },
    "dump": {
        "syntax": "dump ID group-ID style N filename args",
        "styles": ["atom", "custom", "cfg", "dcd", "xtc", "xyz", "image", "movie"],
        "section": "Output Commands",
        "description": "Writes snapshot trajectory files of atom coordinates and per-atom quantities every N timesteps.",
        "details": "dump 1 all custom 1000 traj.lammpstrj id type x y z vx vy vz outputs atom ID, type, unscaled positions, and velocities.",
        "keywords": ["dump", "trajectory", "lammpstrj", "custom dump", "xyz", "vmd", "ovito"]
    },
    "minimize": {
        "syntax": "minimize etol ftol maxiter maxeval",
        "styles": [],
        "section": "Energy Minimization",
        "description": "Performs energy minimization of the system using conjugate gradient or steepest descent.",
        "details": "Relieves overlapping atomic configurations and steric clashes before molecular dynamics integration.",
        "keywords": ["minimize", "energy minimization", "conjugate gradient", "relaxation", "steepest descent"]
    },
    "timestep": {
        "syntax": "timestep dt",
        "styles": [],
        "section": "Time Integration & Ensembles",
        "description": "Sets the time step size for numerical Verlet integration.",
        "details": "For metal units: typical timestep is 0.001 ps (1 fs). For real units: 1.0 fs. For lj units: 0.005 tau.",
        "keywords": ["timestep", "dt", "integration step", "femtoseconds", "picoseconds", "verlet"]
    },
    "run": {
        "syntax": "run N keyword value ...",
        "styles": [],
        "section": "Execution Commands",
        "description": "Executes a molecular dynamics simulation run for N timesteps.",
        "details": "Advances atomic positions and velocities according to active fix integrators and pair forces.",
        "keywords": ["run", "execute simulation", "timesteps", "production run"]
    }
}

BUILTIN_GUIDES = [
    DocChunk(
        chunk_id="guide_lj_potential",
        source_path="LAMMPS Manual → Pair Styles → pair_style lj/cut",
        doc_type="guide",
        section="Pair Styles",
        subsection="lj/cut",
        command_name="pair_style lj/cut",
        title="Lennard-Jones 12-6 Potential (lj/cut)",
        content="""The lj/cut style computes standard 12-6 Lennard-Jones potential:
E = 4 * epsilon * [(sigma/r)^12 - (sigma/r)^6] for r < rc
Syntax: pair_style lj/cut cutoff
pair_coeff I J epsilon sigma [cutoff]
Used extensively for noble gases, model liquids, and coarse-grained polymer systems. In reduced units (units lj), epsilon=1.0, sigma=1.0, and cutoff is commonly 2.5 or 3.0.""",
        keywords=["pair_style lj/cut", "lennard-jones", "12-6", "epsilon", "sigma", "potential formula", "lj"]
    ),
    DocChunk(
        chunk_id="guide_eam_potential",
        source_path="LAMMPS Manual → Pair Styles → pair_style eam",
        doc_type="guide",
        section="Pair Styles",
        subsection="eam",
        command_name="pair_style eam",
        title="Embedded Atom Method (EAM & EAM/Alloy)",
        content="""The Embedded Atom Method (EAM) computes metallic bonding energy:
E_tot = sum_i F_i(rho_i) + 0.5 * sum_{i!=j} phi_{ij}(r_{ij})
where F_i is the embedding energy to place atom i into electron density rho_i, and phi_{ij} is a core-core pair interaction.
Syntax: pair_style eam/alloy
pair_coeff * * Al_zhou.eam.alloy Al
Crucial for metals and alloys (Al, Cu, Ni, Fe, Ti) where many-body electron cloud effects dominate.""",
        keywords=["pair_style eam", "eam/alloy", "embedded atom method", "metallic bonding", "metals", "aluminum", "copper"]
    ),
    DocChunk(
        chunk_id="guide_fix_nvt",
        source_path="LAMMPS Manual → Fixes → fix nvt",
        doc_type="guide",
        section="Fixes",
        subsection="nvt",
        command_name="fix nvt",
        title="NVT Canonical Ensemble (Nose-Hoover Thermostat)",
        content="""Fix nvt performs constant number of particles, volume, and temperature (NVT canonical ensemble) time integration using a Nose-Hoover thermostat chain.
Syntax: fix ID group-ID nvt temp Tstart Tstop Tdamp
- Tstart / Tstop: initial and target temperature.
- Tdamp: temperature damping parameter in time units (typically ~100 timesteps, e.g. 0.1 ps in metal units).
Generates realistic thermal fluctuations and maintains constant kinetic energy distribution.""",
        keywords=["fix nvt", "canonical ensemble", "nose-hoover", "thermostat", "temperature damping", "Tdamp", "thermalization"]
    ),
    DocChunk(
        chunk_id="guide_fix_npt",
        source_path="LAMMPS Manual → Fixes → fix npt",
        doc_type="guide",
        section="Fixes",
        subsection="npt",
        command_name="fix npt",
        title="NPT Isothermal-Isobaric Ensemble",
        content="""Fix npt performs constant N, P, T time integration using coupled Nose-Hoover thermostat and barostat.
Syntax: fix ID group-ID npt temp Tstart Tstop Tdamp iso Pstart Pstop Pdamp
- Pdamp: pressure damping parameter in time units (typically ~1000 timesteps, e.g. 1.0 ps in metal units).
Used to equilibrate box volume and relieve internal stresses during phase changes or mechanical thermal expansion.""",
        keywords=["fix npt", "isothermal-isobaric", "barostat", "pressure damping", "Pdamp", "box expansion", "density equilibration"]
    ),
    DocChunk(
        chunk_id="guide_compute_rdf",
        source_path="LAMMPS Manual → Computes → compute rdf",
        doc_type="guide",
        section="Computes",
        subsection="rdf",
        command_name="compute rdf",
        title="Radial Distribution Function g(r)",
        content="""Compute rdf calculates the radial distribution function (RDF) or pair correlation function g(r) for atomic pairs.
Syntax: compute ID group-ID rdf Nbin itype1 jtype1 ...
Used with fix ave/time to compute time-averaged structural pair ordering in liquids, glasses, and crystalline lattice phase changes.""",
        keywords=["compute rdf", "radial distribution function", "g(r)", "pair correlation", "structural analysis"]
    ),
    DocChunk(
        chunk_id="guide_error_lost_atoms",
        source_path="LAMMPS Manual → Errors → Lost Atoms",
        doc_type="guide",
        section="Troubleshooting",
        subsection="lost_atoms",
        command_name="ERROR: Lost atoms",
        title="Troubleshooting 'Lost atoms' Error",
        content="""The 'ERROR: Lost atoms' occurs when an atom moves outside the simulation box boundaries or moves more than one processor sub-domain within a single timestep.
Common causes & fixes:
1. Timestep is too large (e.g. >2 fs for metals or >0.005 for LJ). Reduce timestep.
2. Initial atom overlap / steric clash. Run 'minimize 1.0e-4 1.0e-6 1000 10000' before running dynamics.
3. Unphysical thermostat damping. Ensure Tdamp is at least 100*timestep.
4. Non-periodic boundary without atom containment. Use periodic boundaries 'boundary p p p' or reflective walls.""",
        keywords=["ERROR: Lost atoms", "lost atoms", "simulation divergence", "timestep reduction", "steric clash", "energy minimization"]
    ),
    DocChunk(
        chunk_id="guide_shah_mdtransport",
        source_path="Shah Research Group → MDTransport Suite",
        doc_type="guide",
        section="Transport Properties",
        subsection="mdtransport",
        command_name="mdtransport",
        title="Shah Research Group MDTransport Suite",
        content="""MDTransport is a specialized computational package developed by the Shah Research Group (Prof. Jindal K. Shah) for computing transport properties of complex fluids, ionic liquids, and electrolytes from LAMMPS molecular dynamics simulations.
Calculated transport properties include:
- Self-diffusion coefficients (D_i) via Mean Squared Displacement (Einstein relation)
- Ionic conductivity (sigma) via Nernst-Einstein and Green-Kubo current autocorrelation
- Shear viscosity (eta) via Green-Kubo pressure tensor integration
- Radial distribution functions (g(r)) with automated cutoffs and species binning.
Command line flags: --lamp for direct LAMMPS dump parsing, --com for center of mass tracking, --species for multi-component systems, --rcut, and --rbin.""",
        keywords=["mdtransport", "shah research group", "diffusion coefficient", "ionic conductivity", "viscosity", "green-kubo", "einstein relation", "transport properties"]
    )
]

BUILTIN_EXAMPLES = [
    ExampleChunk(
        example_id="ex_lj_liquid",
        topic="Lennard-Jones Liquid Equilibration",
        title="Lennard-Jones Liquid Equilibration",
        category="Liquid Physics",
        description="Equilibrates a 3D Lennard-Jones liquid in reduced units at reduced temperature T=0.85 and density rho=0.84.",
        script="""units           lj
atom_style      atomic
boundary        p p p

lattice         fcc 0.8442
region          box block 0 5 0 5 0 5
create_box      1 box
create_atoms    1 box
mass            1 1.0

pair_style      lj/cut 2.5
pair_coeff      1 1 1.0 1.0 2.5

velocity        all create 0.85 87287 dist gaussian
fix             1 all nvt temp 0.85 0.85 0.5

thermo          50
thermo_style    custom step temp pe ke etotal press vol

run             500""",
        materials=["Lennard-Jones", "Noble Gas", "Argon"],
        commands_used=["units", "lattice", "pair_style lj/cut", "fix nvt", "velocity", "thermo", "run"],
        tags=["lj", "lennard-jones", "liquid", "nvt", "reduced units"]
    ),
    ExampleChunk(
        example_id="ex_al_melting",
        topic="Aluminum FCC High-Temperature Melting",
        title="Aluminum FCC High-Temperature Melting",
        category="Metallurgy & Phase Transitions",
        description="Melts an FCC Aluminum supercell from 300 K to 1200 K using an EAM potential.",
        script="""units           metal
atom_style      atomic
boundary        p p p

lattice         fcc 4.05
region          box block 0 4 0 4 0 4
create_box      1 box
create_atoms    1 box
mass            1 26.98

pair_style      eam/alloy
pair_coeff      * * Al_zhou.eam.alloy Al

velocity        all create 300.0 4928459 dist gaussian
fix             1 all nvt temp 300.0 1200.0 0.1

thermo          50
thermo_style    custom step temp pe ke etotal press vol

run             1000""",
        materials=["Aluminum", "Al"],
        commands_used=["units metal", "lattice fcc", "pair_style eam/alloy", "fix nvt", "run"],
        tags=["aluminum", "melting", "eam", "fcc", "phase transition"]
    )
]