"""Unit tests for Liquid-State Transport Modules, Templates, and Validation Rules."""
import unittest
from app.lammps.viscosity import calculate_green_kubo_viscosity, generate_green_kubo_commands
from app.lammps.diffusion import calculate_diffusion_coefficient, generate_msd_commands
from app.generation.templates import template_water_liquid, template_lj_fluid, template_molten_metal
from app.lammps.validator import ScriptValidator


class TestLiquidStateModules(unittest.TestCase):
    """Test suite for liquid-specific calculations, templates, and protocol validation."""

    def setUp(self):
        self.validator = ScriptValidator()

    # ── Viscosity Module Tests (Green-Kubo) ──────────────────────────
    def test_green_kubo_viscosity_calculation(self):
        # Synthetic decaying correlation data: C(t) = exp(-t/100)
        import math
        time_pts = [float(i * 5) for i in range(100)]  # 0 to 495 fs
        acf_pxy = [math.exp(-t / 100.0) for t in time_pts]
        acf_pxz = [0.98 * math.exp(-t / 100.0) for t in time_pts]
        acf_pyz = [1.02 * math.exp(-t / 100.0) for t in time_pts]

        res = calculate_green_kubo_viscosity(
            time_pts=time_pts,
            acf_pxy=acf_pxy,
            acf_pxz=acf_pxz,
            acf_pyz=acf_pyz,
            volume=8000.0,
            temp=300.0,
            units="real"
        )
        self.assertGreater(res["viscosity_pa_s"], 0.0)
        self.assertGreater(res["viscosity_cp"], 0.0)
        self.assertEqual(res["components_averaged"], 3)
        self.assertIn("scientific_note", res)

    def test_green_kubo_commands_generation(self):
        cmds = generate_green_kubo_commands(sample_interval=1, num_samples=50, corr_length=50)
        self.assertIn("variable        pxy equal pxy", cmds)
        self.assertIn("variable        pxz equal pxz", cmds)
        self.assertIn("variable        pyz equal pyz", cmds)
        self.assertIn("fix             fGK all ave/correlate", cmds)

    # ── Diffusion Module Tests (Einstein MSD) ────────────────────────
    def test_core_diffusion_calculation(self):
        # Linear MSD: MSD(t) = 6 * D * t + noise. Let D = 2.5e-9 m^2/s = 0.25 A^2/ps
        # Slope = 6 * D = 1.5 A^2/ps
        time_ps = [float(i) for i in range(50)]
        msd_angstrom2 = [1.5 * t for t in time_ps]

        res = calculate_diffusion_coefficient(time_ps, msd_angstrom2, fit_start_fraction=0.2)
        self.assertAlmostEqual(res["slope_angstrom2_ps"], 1.5, places=3)
        # D = 1.5 / 6 * 1e-8 m^2/s = 2.5e-9 m^2/s
        self.assertAlmostEqual(res["diffusion_coefficient_m2_s"], 2.5e-9, places=12)
        self.assertGreaterEqual(res["r_squared"], 0.99)

    def test_msd_commands_generation(self):
        cmds = generate_msd_commands(group="all", compute_id="cMSD")
        self.assertIn("compute         cMSD all msd", cmds)
        self.assertIn("fix             fMSD all ave/time", cmds)

    # ── Template & Protocol Tests ────────────────────────────────────
    def test_spce_water_template_syntax(self):
        script = template_water_liquid(
            temp=300.0,
            ensemble="NVT",
            timestep=1.0,
            nsteps=1000,
            kspace_choice="pppm",
            compute_rdf=True,
            compute_msd=True
        )
        val = self.validator.validate_static(script)
        self.assertTrue(val["valid"])
        self.assertEqual(len(val["errors"]), 0)
        self.assertIn("fix             rigidH2O all shake 0.0001 20 0 b 1 a 1", script)
        self.assertIn("pair_style      lj/cut/coul/long 9.8", script)
        self.assertIn("kspace_style    pppm 1.0e-4", script)
        self.assertIn("compute         cRDF all rdf", script)
        self.assertIn("compute         cMSD all msd", script)

    def test_spce_water_cutoff_tradeoff_documented(self):
        script = template_water_liquid(
            temp=300.0,
            ensemble="NVT",
            kspace_choice="cut"
        )
        self.assertIn("pair_style      lj/cut/coul/cut 9.8", script)
        self.assertIn("ELECTROSTATICS WARNING", script)
        self.assertIn("truncated", script)
        self.assertNotIn("kspace_style", script)

    def test_molten_metal_liquid_protocol(self):
        script = template_molten_metal(
            material="Copper",
            element="Cu",
            lattice_a=3.615,
            mass=63.546,
            pot_file="Cu_zhou.eam.alloy",
            ensemble="NVE",
            t_stop=1500.0,
            nsteps=2000
        )
        val = self.validator.validate_static(script)
        self.assertTrue(val["valid"])
        # Liquid protocol: superheat melt at T_hot = max(1.5*T_m, T+300) -> liquid equilibration -> NVE production
        self.assertIn("fix             melt all npt temp 300.0 1800.0", script)
        self.assertIn("fix             eq all npt temp 1500.0 1500.0", script)
        self.assertIn("fix             prod all nve", script)

    # ── Validator Edge Cases (Issues #17 & #18) ──────────────────────
    def test_validator_detects_non_integrating_fix(self):
        # Script with only fix setforce (non-integrating) should warn
        script = """units lj
atom_style atomic
boundary p p p
lattice fcc 0.84
region box block 0 4 0 4 0 4
create_box 1 box
create_atoms 1 box
pair_style lj/cut 2.5
pair_coeff 1 1 1.0 1.0 2.5
velocity all create 1.0 1234
timestep 0.005
fix 1 all setforce 0.0 0.0 0.0
run 100"""
        val = self.validator.validate_static(script)
        self.assertTrue(val["valid"])
        self.assertTrue(any("No active time-integrating 'fix'" in w for w in val["warnings"]))

    def test_validator_warns_on_missing_velocity_in_dynamics(self):
        # Script with run but no velocity initialization should warn
        script = """units lj
atom_style atomic
boundary p p p
lattice fcc 0.84
region box block 0 4 0 4 0 4
create_box 1 box
create_atoms 1 box
pair_style lj/cut 2.5
pair_coeff 1 1 1.0 1.0 2.5
timestep 0.005
fix 1 all nvt temp 1.0 1.0 0.5
run 100"""
        val = self.validator.validate_static(script)
        self.assertTrue(val["valid"])
        self.assertTrue(any("velocity" in w.lower() for w in val["warnings"]))

    def test_validator_warns_on_missing_explicit_timestep(self):
        # Script with no timestep declaration should warn
        script = """units lj
atom_style atomic
boundary p p p
lattice fcc 0.84
region box block 0 4 0 4 0 4
create_box 1 box
create_atoms 1 box
pair_style lj/cut 2.5
pair_coeff 1 1 1.0 1.0 2.5
velocity all create 1.0 1234
fix 1 all nvt temp 1.0 1.0 0.5
run 100"""
        val = self.validator.validate_static(script)
        self.assertTrue(val["valid"])
        self.assertTrue(any("No explicit 'timestep' set" in w for w in val["warnings"]))


if __name__ == "__main__":
    unittest.main()
