"""Intent Detection and Structured Scientific Requirement Extractor."""
import re
from typing import Dict, Any, List

class IntentExtractor:
    """Extracts intent and scientific parameters from natural language prompts."""

    MATERIAL_DATABASE = {
        "aluminum": {"element": "Al", "lattice": "fcc", "a": 4.05, "mass": 26.9815, "potential": "eam/alloy", "units": "metal", "pot_file": "Al_zhou.eam.alloy", "name": "Aluminum"},
        "aluminium": {"element": "Al", "lattice": "fcc", "a": 4.05, "mass": 26.9815, "potential": "eam/alloy", "units": "metal", "pot_file": "Al_zhou.eam.alloy", "name": "Aluminum"},
        "al": {"element": "Al", "lattice": "fcc", "a": 4.05, "mass": 26.9815, "potential": "eam/alloy", "units": "metal", "pot_file": "Al_zhou.eam.alloy", "name": "Aluminum"},
        "copper": {"element": "Cu", "lattice": "fcc", "a": 3.615, "mass": 63.546, "potential": "eam/alloy", "units": "metal", "pot_file": "Cu_zhou.eam.alloy", "name": "Copper"},
        "cu": {"element": "Cu", "lattice": "fcc", "a": 3.615, "mass": 63.546, "potential": "eam/alloy", "units": "metal", "pot_file": "Cu_zhou.eam.alloy", "name": "Copper"},
        "nickel": {"element": "Ni", "lattice": "fcc", "a": 3.52, "mass": 58.6934, "potential": "eam/alloy", "units": "metal", "pot_file": "Ni_u3.eam", "name": "Nickel"},
        "ni": {"element": "Ni", "lattice": "fcc", "a": 3.52, "mass": 58.6934, "potential": "eam/alloy", "units": "metal", "pot_file": "Ni_u3.eam", "name": "Nickel"},
        "iron": {"element": "Fe", "lattice": "bcc", "a": 2.8665, "mass": 55.845, "potential": "eam/fs", "units": "metal", "pot_file": "Fe_mm.eam.fs", "name": "Iron"},
        "fe": {"element": "Fe", "lattice": "bcc", "a": 2.8665, "mass": 55.845, "potential": "eam/fs", "units": "metal", "pot_file": "Fe_mm.eam.fs", "name": "Iron"},
        "silicon": {"element": "Si", "lattice": "diamond", "a": 5.431, "mass": 28.0855, "potential": "tersoff", "units": "metal", "pot_file": "Si.tersoff", "name": "Silicon"},
        "si": {"element": "Si", "lattice": "diamond", "a": 5.431, "mass": 28.0855, "potential": "tersoff", "units": "metal", "pot_file": "Si.tersoff", "name": "Silicon"},
        "argon": {"element": "Ar", "lattice": "fcc", "a": 5.256, "mass": 39.948, "potential": "lj/cut", "units": "real", "pot_file": None, "name": "Argon"},
        "ar": {"element": "Ar", "lattice": "fcc", "a": 5.256, "mass": 39.948, "potential": "lj/cut", "units": "real", "pot_file": None, "name": "Argon"},
        "lennard-jones": {"element": "LJ", "lattice": "fcc", "a": 0.8442, "mass": 1.0, "potential": "lj/cut", "units": "lj", "pot_file": None, "name": "Lennard-Jones"},
        "lj": {"element": "LJ", "lattice": "fcc", "a": 0.8442, "mass": 1.0, "potential": "lj/cut", "units": "lj", "pot_file": None, "name": "Lennard-Jones"},
        "water": {"element": "TIP4P", "lattice": "none", "a": None, "mass": 18.015, "potential": "lj/cut/coul/long", "units": "real", "pot_file": None, "name": "Water"}
    }

    def extract_intent(self, text: str) -> Dict[str, Any]:
        lower = text.lower()

        # Intent Classification
        if any(w in lower for w in ["error", "illegal", "lost atoms", "out of range", "failed", "crash", "segmentation"]):
            intent = "DIAGNOSE_ERROR"
        elif any(w in lower for w in ["create", "generate", "build", "write script", "input script", "simulate", "model"]):
            intent = "GENERATE_SCRIPT"
        elif any(w in lower for w in ["did temperature stabilize", "what is final energy", "analyze output", "parse log", "highest temperature", "thermo output"]):
            intent = "ANALYZE_OUTPUT"
        elif any(w in lower for w in ["how to", "how do i", "what is", "syntax", "difference between", "explain"]):
            intent = "DOC_QUESTION"
        else:
            intent = "GENERAL_QUERY"

        # Scientific Requirement Extraction
        material_key = None
        for k in self.MATERIAL_DATABASE:
            if re.search(r'\b' + re.escape(k) + r'\b', lower):
                material_key = k
                break

        sim_type = "equilibration"
        if "melt" in lower or "melting" in lower:
            sim_type = "melting"
        elif "tensile" in lower or "deformation" in lower or "strain" in lower:
            sim_type = "tensile_deformation"
        elif "rdf" in lower or "radial distribution" in lower:
            sim_type = "rdf_structure"
        elif "diffusion" in lower or "msd" in lower:
            sim_type = "diffusion_transport"

        # Ensemble
        ensemble = "NVT"
        if "npt" in lower:
            ensemble = "NPT"
        elif "nve" in lower:
            ensemble = "NVE"
        elif "langevin" in lower:
            ensemble = "LANGEVIN"

        # Temperatures
        temp_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:k\b|kelvin)', lower)
        target_temp = float(temp_match.group(1)) if temp_match else (300.0 if (material_key and self.MATERIAL_DATABASE[material_key]["units"] == "metal") else 1.0)

        # Timestep
        dt_match = re.search(r'timestep\s*(?:of)?\s*(\d+(?:\.\d+)?)', lower)
        dt = float(dt_match.group(1)) if dt_match else None

        # Missing parameters detection for safe scientific planning
        missing = []
        if intent == "GENERATE_SCRIPT":
            if not material_key:
                missing.append("Material / System Composition (e.g., Aluminum, Copper, Silicon, Lennard-Jones)")
            if sim_type == "tensile_deformation" and "strain rate" not in lower and "erate" not in lower:
                missing.append("Strain rate / Deformation velocity")

        return {
            "intent": intent,
            "raw_text": text,
            "material_name": material_key or ("Lennard-Jones" if "lj" in lower else None),
            "material_info": self.MATERIAL_DATABASE.get(material_key),
            "simulation_type": sim_type,
            "ensemble": ensemble,
            "temperature": target_temp,
            "timestep": dt,
            "missing_parameters": missing
        }
