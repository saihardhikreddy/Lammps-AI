"""Simulation Stage & Workflow Planner."""
from typing import Dict, Any, List

class SimulationPlanner:
    """Plans multi-stage simulation workflows and parameters for physical accuracy."""

    def create_plan(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        sim_type = spec.get("simulation_type", "melting").lower()
        mat_info = spec.get("material_info") or {}
        ensemble = spec.get("ensemble", "NVT").upper()
        temp = spec.get("temperature", 300.0)

        stages = ["System Initialization", "Lattice & Box Creation", "Force Field Definition", "Energy Minimization"]

        if "tensile" in sim_type:
            stages.extend(["Thermal Equilibration (NVT/NPT)", "Uniaxial Deformation (fix deform)", "Stress-Strain Output"])
            description = f"Uniaxial tensile deformation under constant strain rate in {ensemble} ensemble."
        elif "melting" in sim_type:
            stages.extend([f"Thermal Equilibration at {temp} K", "Heating & Phase Change Ramp", "Thermodynamic Sampling"])
            description = f"Thermal melting simulation ramped to high temperature in {ensemble} ensemble."
        elif "diffusion" in sim_type or "transport" in sim_type:
            stages.extend(["Equilibration Run", "MSD / Velocity Autocorrelation Sampling", "Green-Kubo / Einstein Transport Calculation"])
            description = f"Transport property and diffusion coefficient calculation in {ensemble} ensemble."
        else:
            stages.extend([f"Equilibration ({ensemble})", "Production Trajectory Sampling"])
            description = f"Standard molecular dynamics equilibration in {ensemble} ensemble."

        return {
            "simulation_type": sim_type,
            "ensemble": ensemble,
            "target_temperature": temp,
            "stages": stages,
            "description": description,
            "material": mat_info.get("name", spec.get("material_name", "General System"))
        }
