"""Intent Detection and Structured Scientific Requirement Extractor for Liquid-State MD.

Uses flexible regex parsing to extract user values (temperatures, atom counts, ensembles,
timesteps, dump/thermo intervals) into a plain dataclass. Standard library only.
"""
import re
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional


@dataclass
class SimulationParameters:
    """Simulation parameters extracted directly from the user's request."""
    material: Optional[str] = None               # identified material or species
    target_temperature: Optional[float] = None   # K, or reduced units for LJ
    start_temperature: Optional[float] = None    # start of a heating/cooling range
    quench_rate: Optional[float] = None          # K/s or K/ps (not used by templates)
    atom_count: Optional[int] = None             # approximate particle count requested
    ensemble: Optional[str] = "NVT"              # NVT, NPT, NVE, LANGEVIN
    ensemble_specified: bool = False             # True if the user named the ensemble
    timestep: Optional[float] = None             # numeric value as typed by the user
    timestep_unit: Optional[str] = None          # "fs", "ps", "tau" or None if not given
    dump_interval: Optional[int] = None          # steps between trajectory frames
    thermo_interval: Optional[int] = None        # steps between thermo lines
    simulation_type: str = "equilibration"
    user_temperature_specified: bool = False

    def model_dump(self) -> Dict[str, Any]:
        """Compatibility with the previous pydantic model."""
        return asdict(self)


class IntentExtractor:
    """Extracts intent and scientific parameters from natural language prompts for liquid-state simulations."""

    MATERIAL_DATABASE = {
        # Molten Metals (repurposed strictly for post-melt liquid simulation)
        "aluminum": {"element": "Al", "lattice": "fcc", "a": 4.05, "mass": 26.9815, "potential": "eam/alloy", "units": "metal", "pot_file": "Al_zhou.eam.alloy", "name": "Aluminum", "category": "molten_metal", "t_melt": 933.47},
        "aluminium": {"element": "Al", "lattice": "fcc", "a": 4.05, "mass": 26.9815, "potential": "eam/alloy", "units": "metal", "pot_file": "Al_zhou.eam.alloy", "name": "Aluminum", "category": "molten_metal", "t_melt": 933.47},
        "al": {"element": "Al", "lattice": "fcc", "a": 4.05, "mass": 26.9815, "potential": "eam/alloy", "units": "metal", "pot_file": "Al_zhou.eam.alloy", "name": "Aluminum", "category": "molten_metal", "t_melt": 933.47},
        "copper": {"element": "Cu", "lattice": "fcc", "a": 3.615, "mass": 63.546, "potential": "eam/alloy", "units": "metal", "pot_file": "Cu_zhou.eam.alloy", "name": "Copper", "category": "molten_metal", "t_melt": 1357.77},
        "cu": {"element": "Cu", "lattice": "fcc", "a": 3.615, "mass": 63.546, "potential": "eam/alloy", "units": "metal", "pot_file": "Cu_zhou.eam.alloy", "name": "Copper", "category": "molten_metal", "t_melt": 1357.77},
        "nickel": {"element": "Ni", "lattice": "fcc", "a": 3.52, "mass": 58.6934, "potential": "eam", "units": "metal", "pot_file": "Ni_u3.eam", "name": "Nickel", "category": "molten_metal", "t_melt": 1728.0},
        "ni": {"element": "Ni", "lattice": "fcc", "a": 3.52, "mass": 58.6934, "potential": "eam", "units": "metal", "pot_file": "Ni_u3.eam", "name": "Nickel", "category": "molten_metal", "t_melt": 1728.0},
        "iron": {"element": "Fe", "lattice": "bcc", "a": 2.8665, "mass": 55.845, "potential": "eam/fs", "units": "metal", "pot_file": "Fe_mm.eam.fs", "name": "Iron", "category": "molten_metal", "t_melt": 1811.0},
        "fe": {"element": "Fe", "lattice": "bcc", "a": 2.8665, "mass": 55.845, "potential": "eam/fs", "units": "metal", "pot_file": "Fe_mm.eam.fs", "name": "Iron", "category": "molten_metal", "t_melt": 1811.0},
        # Noble and Model Liquids
        "argon": {"element": "Ar", "lattice": "fcc", "a": 5.256, "mass": 39.948, "potential": "lj/cut", "units": "real", "pot_file": None, "name": "Argon", "category": "noble_liquid", "t_melt": 83.8, "t_boil": 87.3},
        "ar": {"element": "Ar", "lattice": "fcc", "a": 5.256, "mass": 39.948, "potential": "lj/cut", "units": "real", "pot_file": None, "name": "Argon", "category": "noble_liquid", "t_melt": 83.8, "t_boil": 87.3},
        "lennard-jones": {"element": "LJ", "lattice": "fcc", "a": 0.8442, "mass": 1.0, "potential": "lj/cut", "units": "lj", "pot_file": None, "name": "Lennard-Jones", "category": "model_liquid", "t_melt": 0.7, "t_boil": 1.1},
        "lj": {"element": "LJ", "lattice": "fcc", "a": 0.8442, "mass": 1.0, "potential": "lj/cut", "units": "lj", "pot_file": None, "name": "Lennard-Jones", "category": "model_liquid", "t_melt": 0.7, "t_boil": 1.1},
        # Molecular Liquid Water (SPC/E Model)
        "water": {"element": "SPC/E", "lattice": "none", "a": None, "mass": 18.015, "potential": "lj/cut/coul/long", "units": "real", "pot_file": None, "name": "Water", "category": "molecular_liquid", "t_melt": 273.15, "t_boil": 373.15},
        "h2o": {"element": "SPC/E", "lattice": "none", "a": None, "mass": 18.015, "potential": "lj/cut/coul/long", "units": "real", "pot_file": None, "name": "Water", "category": "molecular_liquid", "t_melt": 273.15, "t_boil": 373.15}
    }

    def extract_structured_parameters(self, text: str) -> SimulationParameters:
        """Extracts dynamic simulation parameters cleanly using Pydantic."""
        lower = text.lower()

        # Material
        material_key = None
        for k in sorted(self.MATERIAL_DATABASE.keys(), key=lambda x: -len(x)):
            if re.search(r'\b' + re.escape(k) + r'\b', lower):
                material_key = k
                break

        # Temperatures (Range or single)
        user_temp_specified = False
        target_temp = None
        start_temp = None

        # Check for range: "from 2000 K to 300 K" or "quench 2000 to 300 K"
        range_match = re.search(r'(?:from|quench|cool(?:ing)?)\s*(\d+(?:\.\d+)?)\s*(?:k)?\s*(?:to|down to)\s*(\d+(?:\.\d+)?)\s*(?:k\b|kelvin)', lower)
        if range_match:
            start_temp = float(range_match.group(1))
            target_temp = float(range_match.group(2))
            user_temp_specified = True
        else:
            temp_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:k\b|kelvin)', lower)
            if temp_match:
                target_temp = float(temp_match.group(1))
                user_temp_specified = True
            else:
                # Baseline fallback only if no temperature specified; marked as not user-specified
                mat_entry = self.MATERIAL_DATABASE.get(material_key)
                if mat_entry:
                    if mat_entry.get("category") == "molten_metal":
                        target_temp = mat_entry.get("t_melt", 1000.0) + 100.0
                    elif mat_entry.get("name") == "Argon":
                        target_temp = 85.0
                    elif mat_entry.get("name") == "Water":
                        target_temp = 300.0
                    elif mat_entry.get("units") == "lj":
                        target_temp = 1.0
                    else:
                        target_temp = 300.0
                else:
                    target_temp = 300.0

        # Simulation Type
        is_tensile = bool(re.search(r'\b(tensile|deformation|strain|stress-strain|erate)\b', lower))
        if is_tensile:
            sim_type = "unsupported_tensile"
        elif range_match or "quench" in lower or "cooling rate" in lower:
            sim_type = "quench"
        elif "viscosity" in lower or "green-kubo" in lower or "shear viscosity" in lower:
            sim_type = "viscosity_transport"
        elif "rdf" in lower or "radial distribution" in lower:
            sim_type = "rdf_structure"
        elif "diffusion" in lower or "msd" in lower:
            sim_type = "diffusion_transport"
        elif "melt" in lower or "melting" in lower or "molten" in lower:
            sim_type = "melting"
        else:
            sim_type = "equilibration"

        # Ensemble
        ensemble = "NVT"
        ensemble_specified = True
        if re.search(r"\bnpt\b", lower):
            ensemble = "NPT"
        elif re.search(r"\bnve\b|microcanonical", lower):
            ensemble = "NVE"
        elif "langevin" in lower:
            ensemble = "LANGEVIN"
        elif re.search(r"\bnvt\b|canonical|nose-hoover|nos[eé]-hoover", lower):
            ensemble = "NVT"
        else:
            ensemble_specified = False

        # Atom count (e.g., "5000 atoms", "32000 particles", "N=10000")
        atom_count = None
        atom_match = re.search(r'\b(\d+)\s*(?:atoms|particles|molecules)\b|\bn\s*=\s*(\d+)\b', lower)
        if atom_match:
            val = atom_match.group(1) or atom_match.group(2)
            atom_count = int(val)

        # Quench Rate (e.g. "quench rate 1e12 K/s", "cooling rate of 0.5 K/ps")
        quench_rate = None
        qr_match = re.search(r'(?:quench|cooling)\s*(?:rate)?\s*(?:of)?\s*([0-9.eE+-]+)\s*(?:k/s|k/ps)?', lower)
        if qr_match:
            try:
                quench_rate = float(qr_match.group(1))
            except ValueError:
                pass

        # Timestep (e.g., "timestep 0.001", "timestep of 0.5 fs", "dt = 2 fs")
        dt_match = re.search(
            r'(?:timestep|time step|\bdt)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?(?:e-?\d+)?)\s*(fs|ps|tau)?\b', lower)
        dt = float(dt_match.group(1)) if dt_match else None
        dt_unit = dt_match.group(2) if dt_match and dt_match.group(2) else None

        # Dump Interval (e.g., "dump every 250", "dump interval 500")
        dump_interval = None
        dump_match = re.search(r'dump\s*(?:every|interval)?\s*(\d+)', lower)
        if dump_match:
            dump_interval = int(dump_match.group(1))

        # Thermo Interval (e.g., "thermo 100", "thermo every 500")
        thermo_interval = None
        thermo_match = re.search(r'thermo\s*(?:every|interval)?\s*(\d+)', lower)
        if thermo_match:
            thermo_interval = int(thermo_match.group(1))

        return SimulationParameters(
            material=material_key or ("Lennard-Jones" if "lj" in lower else None),
            target_temperature=target_temp,
            start_temperature=start_temp,
            quench_rate=quench_rate,
            atom_count=atom_count,
            ensemble=ensemble,
            ensemble_specified=ensemble_specified,
            timestep=dt,
            timestep_unit=dt_unit,
            dump_interval=dump_interval,
            thermo_interval=thermo_interval,
            simulation_type=sim_type,
            user_temperature_specified=user_temp_specified
        )

    def extract_intent(self, text: str) -> Dict[str, Any]:
        """Classifies intent and extracts requirements into standard dictionary format."""
        lower = text.lower()
        params = self.extract_structured_parameters(text)

        # Intent Classification
        if any(w in lower for w in ["error", "illegal", "lost atoms", "out of range", "failed", "crash", "segmentation"]):
            intent = "DIAGNOSE_ERROR"
        elif (
            any(w in lower for w in [
                "create", "generate", "build", "write script", "input script", "simulate", "model",
                "need a script", "want a script", "give me a script", "make a script", "prepare a script",
                "script for", "script to", "script of", "provide a script", "run a simulation"
            ])
            or bool(re.search(r'\b(write|need|want|give|make|provide|prepare|get)\b.*?\bscript\b', lower))
            or ("script" in lower and (params.material is not None or any(m in lower for m in ["liquid", "fluid", "metal", "molten", "water", "argon", "copper", "aluminum", "nickel", "iron", "lj"])))
            # "Calculate the diffusion coefficient of liquid argon at 85 K" is a request to run one
            or (bool(re.search(r'\b(calculate|compute|measure|estimate|determine|obtain|run)\b', lower))
                and params.material is not None
                and not re.search(r'^\s*(how|what|why|which|explain)\b', lower))
        ):
            intent = "GENERATE_SCRIPT"
        elif any(w in lower for w in ["did temperature stabilize", "what is final energy", "analyze output", "parse log", "highest temperature", "thermo output"]):
            intent = "ANALYZE_OUTPUT"
        elif any(w in lower for w in ["how to", "how do i", "what is", "syntax", "difference between", "explain"]):
            intent = "DOC_QUESTION"
        else:
            intent = "GENERAL_QUERY"

        # Missing parameters detection
        missing = []
        if intent == "GENERATE_SCRIPT" and params.simulation_type != "unsupported_tensile":
            if not params.material:
                missing.append("Material / Liquid System (e.g., Water, Argon, Lennard-Jones, Molten Aluminum)")

        material_key = params.material.lower() if params.material else None

        return {
            "intent": intent,
            "raw_text": text,
            "material_name": params.material,
            "material_info": self.MATERIAL_DATABASE.get(material_key),
            "simulation_type": params.simulation_type,
            "ensemble": params.ensemble,
            "ensemble_specified": params.ensemble_specified,
            "timestep_unit": params.timestep_unit,
            "temperature": params.target_temperature,
            "start_temperature": params.start_temperature,
            "quench_rate": params.quench_rate,
            "atom_count": params.atom_count,
            "timestep": params.timestep,
            "dump_interval": params.dump_interval,
            "thermo_interval": params.thermo_interval,
            "user_temperature_specified": params.user_temperature_specified,
            "missing_parameters": missing,
            "structured_params": asdict(params)
        }
