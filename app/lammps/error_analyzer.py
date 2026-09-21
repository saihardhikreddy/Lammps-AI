"""Diagnostic Error Analysis Engine for LAMMPS Simulation Failures."""
import re
from typing import Dict, Any, List, Optional
from app.knowledge.retriever import LocalKnowledgeRetriever

ERROR_DATABASE = [
    {
        "pattern": r"lost atoms.*original.*current",
        "command": "timestep",
        "cause": "Atoms moved too far in a single timestep and flew outside the simulation domain or neighbor list boundaries.",
        "scientific_reason": "High initial interatomic forces, overlapping atomic positions, or too large a timestep causes extreme velocities (atomic explosion).",
        "suggested_fix": "1. Perform energy minimization with 'minimize 1.0e-4 1.0e-6 1000 10000' before MD.\n2. Reduce the timestep size (e.g., from 0.002 ps to 0.0005 ps in metal units).\n3. Rebuild neighbor lists more frequently: 'neigh_modify delay 0 every 1 check yes'.",
        "patch_example": """# 1. Relax initial atomic overlaps
minimize        1.0e-4 1.0e-6 1000 10000

# 2. Use stable timestep
timestep        0.001

# 3. Dynamic neighbor list rebuilding
neighbor        2.0 bin
neigh_modify    delay 0 every 1 check yes"""
    },
    {
        "pattern": r"out of range atoms.*cannot compute pppm",
        "command": "kspace_style",
        "cause": "Charged atoms moved outside the processor grid during long-range PPPM electrostatic calculation.",
        "scientific_reason": "Non-periodic boundary conditions in a charged system, unrelaxed charged overlap, or charge unbalance.",
        "suggested_fix": "1. Ensure periodic boundary conditions: 'boundary p p p'.\n2. Verify total charge neutrality of the system.\n3. Run energy minimization before dynamic integration.",
        "patch_example": """boundary        p p p
kspace_style    pppm 1.0e-4
minimize        1.0e-4 1.0e-6 1000 10000"""
    },
    {
        "pattern": r"illegal.*pair_style",
        "command": "pair_style",
        "cause": "Invalid arguments or unrecognized style for pair_style command.",
        "scientific_reason": "The pair style syntax requires cutoff parameters or specific flags corresponding to the style.",
        "suggested_fix": "Check pair_style manual syntax. For cutoff styles: 'pair_style lj/cut 2.5'. For EAM: 'pair_style eam/alloy'.",
        "patch_example": """pair_style      lj/cut 2.5
pair_coeff      1 1 1.0 1.0 2.5"""
    },
    {
        "pattern": r"illegal.*fix",
        "command": "fix",
        "cause": "Incorrect number of arguments or parameter ordering in fix definition.",
        "scientific_reason": "Fix command requires: 'fix ID group-ID style args'.",
        "suggested_fix": "For NVT: 'fix 1 all nvt temp Tstart Tstop Tdamp'. Ensure Tdamp is positive (e.g. 0.1 ps).",
        "patch_example": """# fix ID group-ID nvt temp Tstart Tstop Tdamp
fix             1 all nvt temp 300.0 300.0 0.1"""
    },
    {
        "pattern": r"cannot open.*file",
        "command": "pair_coeff",
        "cause": "LAMMPS could not locate a potential file or data file on the disk path.",
        "scientific_reason": "The potential file specified in pair_coeff or data file in read_data is missing from the working directory.",
        "suggested_fix": "Copy the required potential file (e.g., Al99.eam.alloy, Cu_u3.eam, Si.tersoff) into the simulation directory.",
        "patch_example": """pair_style      eam/alloy
pair_coeff      * * Al99.eam.alloy Al"""
    },
    {
        "pattern": r"non-numeric.*atom.*coords|\bnan\b",
        "command": "minimize",
        "cause": "Atom coordinates became NaN (Not a Number) or Infinite.",
        "scientific_reason": "Atoms were placed exactly at distance r=0, resulting in infinite Lennard-Jones repulsion V(r) -> infinity.",
        "suggested_fix": "Check initial lattice spacing or run 'minimize' to remove atomic overlaps.",
        "patch_example": """lattice         fcc 4.05
create_atoms    1 box
minimize        1.0e-4 1.0e-6 1000 10000"""
    }
]

class ErrorAnalyzer:
    """Diagnoses simulation errors, retrieves official manual entries, and suggests fixes."""

    def __init__(self, retriever: LocalKnowledgeRetriever):
        self.retriever = retriever

    def analyze(self, error_text: str) -> Dict[str, Any]:
        matched_entry = None
        for entry in ERROR_DATABASE:
            if re.search(entry["pattern"], error_text, re.IGNORECASE):
                matched_entry = entry
                break

        if matched_entry:
            cmd = matched_entry["command"]
            cause = matched_entry["cause"]
            reason = matched_entry["scientific_reason"]
            fix = matched_entry["suggested_fix"]
            patch = matched_entry["patch_example"]
        else:
            # Fallback heuristic parser
            cmd_match = re.search(r"illegal\s+([a-zA-Z0-9_/]+)\s+command", error_text, re.IGNORECASE)
            cmd = cmd_match.group(1) if cmd_match else "command"
            cause = f"LAMMPS reported an error related to `{cmd}`."
            reason = "Syntax mismatch, unsupported style argument, or missing required parameter."
            fix = f"Consult the documentation for '{cmd}' to verify argument ordering and valid options."
            patch = f"# Refer to documentation for '{cmd}'"

        # Retrieve grounded documentation chunks
        doc_results = self.retriever.search(f"{cmd} {error_text}", top_k=2)
        citations = [r[0].source_path for r in doc_results]

        return {
            "error_text": error_text,
            "identified_command": cmd,
            "probable_cause": cause,
            "scientific_reason": reason,
            "suggested_fix": fix,
            "patch_example": patch,
            "documentation_citations": citations
        }
