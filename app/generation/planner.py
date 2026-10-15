"""Simulation Stage & Workflow Planner for Liquid-State MD."""
from typing import Dict, Any, List

class SimulationPlanner:
    """Plans multi-stage simulation workflows and protocols for physically sound liquid simulations."""

    def create_plan(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        sim_type = spec.get("simulation_type", "equilibration").lower()
        mat_info = spec.get("material_info") or {}
        ensemble = spec.get("ensemble", "NVT").upper()
        temp = spec.get("temperature", 300.0)

        stages = ["System Initialization", "Box & Particle Generation", "Force Field Definition", "Energy Minimization / Soft-Start"]

        if sim_type == "unsupported_tensile":
            return {
                "simulation_type": "unsupported_tensile",
                "ensemble": ensemble,
                "target_temperature": temp,
                "stages": ["Unsupported Operation: Solid Mechanics Out of Scope"],
                "description": "Tensile deformation is out of scope for this liquid-state MD assistant.",
                "material": mat_info.get("name", spec.get("material_name", "Unknown"))
            }
        elif "viscosity" in sim_type:
            stages.extend([
                f"NVT Thermal Equilibration at {temp} K",
                f"Production Run ({ensemble}{' - unperturbed dynamics' if ensemble == 'NVE' else ' - thermostatted, biases transport'})",
                "Green-Kubo Stress Tensor Autocorrelation (pxy, pxz, pyz) & Viscosity Integration"
            ])
            description = f"Liquid shear viscosity via the Green-Kubo relation with {ensemble} production."
        elif "diffusion" in sim_type or "transport" in sim_type:
            stages.extend([
                f"NVT Thermal Equilibration at {temp} K",
                f"Production Run ({ensemble}{' - unperturbed dynamics' if ensemble == 'NVE' else ' - thermostatted, biases transport'})",
                "Mean Squared Displacement (MSD) Sampling & Einstein Diffusion Coefficient Fitting"
            ])
            description = f"Self-diffusion coefficient via the Einstein MSD relation with {ensemble} production."
        elif "rdf" in sim_type or "structure" in sim_type:
            stages.extend([
                f"NVT Thermal Equilibration at {temp} K",
                f"Production Sampling ({ensemble} ensemble)",
                "Radial Distribution Function g(r) Time-Averaging"
            ])
            description = f"Liquid structural characterization via Radial Distribution Function g(r) in {ensemble} ensemble."
        elif "melting" in sim_type:
            stages.extend([
                "Superheat Melt of the Starting Crystal (NPT, 0 bar)",
                f"Post-Melt NPT Liquid Equilibration at {temp} K",
                f"Equilibrated Liquid Production Sampling ({ensemble})"
            ])
            description = f"Molten metal: melt, liquid equilibration and {ensemble} production."
        else:
            stages.extend([
                f"NVT Thermal Equilibration at {temp} K (velocity scaling & thermostat)",
                f"Equilibrated Liquid Production Sampling ({ensemble} ensemble)"
            ])
            description = f"Standard liquid molecular dynamics equilibration protocol in {ensemble} ensemble."

        return {
            "simulation_type": sim_type,
            "ensemble": ensemble,
            "target_temperature": temp,
            "stages": stages,
            "description": description,
            "material": mat_info.get("name", spec.get("material_name", "Liquid System"))
        }
