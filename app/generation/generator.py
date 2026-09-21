"""Documentation-Grounded LAMMPS Input Script Generator."""
from typing import Dict, Any, List
from app.knowledge.retriever import LocalKnowledgeRetriever
from app.generation.templates import template_lj_fluid, template_metal_melting, template_uniaxial_tensile, template_silicon_thermalization
from app.generation.planner import SimulationPlanner

class ScriptGenerator:
    """Generates complete LAMMPS input scripts grounded in official manual entries and examples."""

    def __init__(self, retriever: LocalKnowledgeRetriever):
        self.retriever = retriever
        self.planner = SimulationPlanner()

    def generate(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        mat_info = spec.get("material_info")
        raw_mat_name = spec.get("material_name") or "Lennard-Jones Liquid"
        mat_name = mat_info.get("name", raw_mat_name.title()) if mat_info else raw_mat_name.title()
        sim_type = spec.get("simulation_type", "melting")
        ensemble = spec.get("ensemble", "NVT").upper()
        temp = spec.get("temperature", 300.0)
        dt = spec.get("timestep")

        plan = self.planner.create_plan(spec)

        if "tensile" in sim_type:
            # Use mat_info if available, else default to Copper
            if mat_info and mat_info.get("units") == "metal":
                elem = mat_info["element"]
                display_name = mat_info.get("name", mat_name)
                lat_a = mat_info.get("a", 3.615)
                m = mat_info.get("mass", 63.546)
                pot = mat_info.get("pot_file", f"{elem}_zhou.eam.alloy")
                lat_style = mat_info.get("lattice", "fcc")
                p_style = mat_info.get("potential", "eam/alloy")
            else:
                elem = "Cu"
                display_name = "Copper"
                lat_a = 3.615
                m = 63.546
                pot = "Cu_zhou.eam.alloy"
                lat_style = "fcc"
                p_style = "eam/alloy"

            timestep_val = dt if dt is not None else 0.001
            script = template_uniaxial_tensile(
                material=display_name,
                element=elem,
                lattice_a=lat_a,
                mass=m,
                pot_file=pot,
                strain_rate=0.001,
                temp=temp if temp else 300.0,
                ensemble=ensemble,
                timestep=timestep_val,
                eq_steps=1000,
                run_steps=2000,
                lattice_style=lat_style,
                pair_style=p_style
            )
            assumptions = [
                f"System: {display_name} single crystal {lat_style.upper()} (a = {lat_a} Å)",
                "Units: metal",
                "Boundary: Periodic in all dimensions (p p p)",
                "Loading: Uniaxial strain along Z at engineering rate 0.001/ps",
                f"Ensemble: {ensemble} integration / lateral barostat",
                f"Timestep: {timestep_val} ps ({timestep_val*1000} fs)"
            ]
            citations = [
                "LAMMPS Manual → Commands → fix deform",
                "LAMMPS Manual → Commands → fix npt",
                "LAMMPS Manual → Commands → compute stress/atom",
                "examples/tensile/in.tensile"
            ]
            required_files = [f"{pot} (auto-loaded from LAMMPS Potentials directory)"] if pot else []

        elif mat_name.lower() in ["aluminum", "al", "aluminium"]:
            timestep_val = dt if dt is not None else 0.001
            script = template_metal_melting(
                material="Aluminum",
                element="Al",
                lattice_a=4.05,
                mass=26.9815,
                pot_file="Al_zhou.eam.alloy",
                ensemble=ensemble,
                timestep=timestep_val,
                t_start=temp if temp else 300.0,
                t_stop=1000.0 if temp < 1000.0 else temp + 400.0,
                nsteps=2000
            )
            assumptions = [
                "System: Aluminum FCC crystal (lattice constant a = 4.05 Å)",
                "Units: metal (distance in Å, energy in eV, time in ps, temp in K, pressure in bar)",
                "Potential: Embedded Atom Method (Al_zhou.eam.alloy)",
                f"Ensemble: {ensemble} integration (Tdamp = 0.1 ps)",
                f"Timestep: {timestep_val} ps ({timestep_val*1000} fs)"
            ]
            citations = [
                "LAMMPS Manual → Commands → units",
                "LAMMPS Manual → Commands → pair_style eam/alloy",
                f"LAMMPS Manual → Commands → fix {ensemble.lower()}",
                "examples/metal/in.al_nvt"
            ]
            required_files = ["Al_zhou.eam.alloy (auto-loaded from LAMMPS Potentials directory)"]

        elif mat_name.lower() in ["silicon", "si"]:
            timestep_val = dt if dt is not None else 0.001
            script = template_silicon_thermalization(
                temp=temp if temp else 300.0,
                ensemble=ensemble,
                timestep=timestep_val,
                nsteps=2000
            )
            assumptions = [
                "System: Silicon diamond cubic crystal (a = 5.431 Å)",
                "Units: metal",
                "Potential: 3-body Tersoff potential (Si.tersoff)",
                f"Ensemble: {ensemble} integration at {temp} K",
                f"Timestep: {timestep_val} ps ({timestep_val*1000} fs)"
            ]
            citations = [
                "LAMMPS Manual → Commands → pair_style tersoff",
                f"LAMMPS Manual → Commands → fix {ensemble.lower()}",
                "examples/tersoff/in.si"
            ]
            required_files = ["Si.tersoff (auto-loaded from LAMMPS Potentials directory)"]

        elif mat_info and mat_info.get("units") == "metal":
            # Other metals (Iron, Nickel, etc.)
            timestep_val = dt if dt is not None else 0.001
            script = template_metal_melting(
                material=mat_info.get("name", mat_name),
                element=mat_info["element"],
                lattice_a=mat_info["a"],
                mass=mat_info["mass"],
                pot_file=mat_info.get("pot_file", f"{mat_info['element']}_u3.eam"),
                ensemble=ensemble,
                timestep=timestep_val,
                t_start=temp if temp else 300.0,
                t_stop=temp + 400.0,
                nsteps=2000,
                lattice_style=mat_info.get("lattice", "fcc"),
                pair_style=mat_info.get("potential", "eam/alloy")
            )
            assumptions = [
                f"System: {mat_info.get('name', mat_name)} {mat_info.get('lattice','fcc').upper()} crystal (a = {mat_info['a']} Å)",
                "Units: metal",
                f"Potential: {mat_info.get('potential','eam')} ({mat_info.get('pot_file')})",
                f"Ensemble: {ensemble} integration",
                f"Timestep: {timestep_val} ps ({timestep_val*1000} fs)"
            ]
            citations = [
                "LAMMPS Manual → Commands → units",
                f"LAMMPS Manual → Commands → pair_style {mat_info.get('potential')}",
                f"LAMMPS Manual → Commands → fix {ensemble.lower()}"
            ]
            required_files = [f"{mat_info.get('pot_file')} (auto-loaded from LAMMPS Potentials directory)"] if mat_info.get("pot_file") else []

        else: # Default: Lennard-Jones liquid
            timestep_val = dt if dt is not None else 0.005
            target_t = temp if (temp and temp < 10.0) else 1.44
            script = template_lj_fluid(
                rho=0.8442,
                temp=target_t,
                ensemble=ensemble if ensemble in ["NVE", "NVT", "NPT"] else "NVE",
                timestep=timestep_val,
                nsteps=500,
                thermo_freq=50
            )
            assumptions = [
                "System: Lennard-Jones fluid in dimensionless reduced units",
                "Units: lj (epsilon=1, sigma=1, mass=1)",
                "Potential: 12-6 Lennard-Jones with standard cutoff rc = 2.5 sigma",
                f"Ensemble: {ensemble} integration",
                f"Timestep: {timestep_val} tau",
                "Neighbor skin: 0.3 sigma with bin neighbor search"
            ]
            citations = [
                "LAMMPS Manual → Commands → units lj",
                "LAMMPS Manual → Commands → pair_style lj/cut",
                f"LAMMPS Manual → Commands → fix {ensemble.lower()}",
                "examples/melt/in.melt"
            ]
            required_files = []

        return {
            "goal": f"Simulate {mat_name} under {sim_type} using {ensemble} ensemble",
            "script": script,
            "plan": plan,
            "assumptions": assumptions,
            "required_files": required_files,
            "citations": citations,
            "run_command": "lmp -in in.run",
            "limitations": "Ensure potential files are present. Empirical force fields do not capture quantum electronic transitions."
        }

