"""Green-Kubo Shear Viscosity Module for Liquid-State Molecular Dynamics.

Computes liquid shear viscosity from equilibrium stress tensor fluctuations
via the Green-Kubo relation:
    eta = (V / (k_B * T)) * int_0^inf <P_alphabeta(0) * P_alphabeta(t)> dt

Where:
    - V is the system volume
    - T is the thermodynamic temperature
    - P_alphabeta are the off-diagonal components of the pressure tensor:
      (P_xy, P_xz, P_yz)
    - Averaged over all 3 independent shear components for improved statistics.

IMPORTANT SCIENTIFIC NOTE ON CONVERGENCE:
Green-Kubo integration requires very long simulation trajectories (typically hundreds
of thousands to millions of timesteps) or averaging over multiple independent runs.
The long-time tail of the autocorrelation function accumulates statistical noise;
short runs will not yield physically converged viscosity values.
"""
from typing import List, Dict, Any, Optional

# Boltzmann constant in SI units (J / K)
KB_SI = 1.380649e-23


def generate_green_kubo_commands(
    sample_interval: int = 1,
    num_samples: int = 50,
    corr_length: int = 50,
    output_file: str = "profile.gk.2d",
    fix_id: str = "fGK"
) -> str:
    """Generate official LAMMPS input script commands to evaluate stress autocorrelation.
    
    Parameters:
        sample_interval (s): Nevery - evaluate stress tensor every s timesteps
        num_samples (p): Nrepeat - number of samples to average
        corr_length (d): Nfreq - calculate correlation over d timesteps
        output_file: Target file for output autocorrelation profile
        fix_id: LAMMPS fix identifier
    """
    return f"""# ── Green-Kubo Shear Viscosity Sampling ──────────────────────────
# Define variables for off-diagonal pressure tensor components
variable        pxy equal pxy
variable        pxz equal pxz
variable        pyz equal pyz

# Autocorrelate stress tensor components over time
fix             {fix_id} all ave/correlate {sample_interval} {num_samples} {corr_length} &
                v_pxy v_pxz v_pyz type auto file {output_file} ave running
"""


def calculate_green_kubo_viscosity(
    time_pts: List[float],
    acf_pxy: List[float],
    acf_pxz: Optional[List[float]] = None,
    acf_pyz: Optional[List[float]] = None,
    volume: float = 1000.0,
    temp: float = 300.0,
    units: str = "real",
    upper_cutoff_fraction: float = 0.8
) -> Dict[str, Any]:
    """Integrate pressure autocorrelation function to compute shear viscosity.
    
    Parameters:
        time_pts: Time points (fs for real units, ps for metal units, tau for LJ)
        acf_pxy: Autocorrelation of P_xy stress tensor component
        acf_pxz: Optional autocorrelation of P_xz component
        acf_pyz: Optional autocorrelation of P_yz component
        volume: Simulation box volume (Å³ for real/metal, sigma³ for LJ)
        temp: Temperature (K for real/metal, T* for LJ)
        units: LAMMPS units style ('real', 'metal', 'lj')
        upper_cutoff_fraction: Fraction of ACF to integrate before tail noise dominates
        
    Returns:
        Dictionary with integrated shear viscosity in Pa·s and cP (mPa·s),
        running integral, and scientific convergence notes.
    """
    n = len(time_pts)
    if n < 2 or len(acf_pxy) < 2 or temp <= 0:
        return {
            "viscosity_pa_s": 0.0,
            "viscosity_cp": 0.0,
            "units": units,
            "converged": False,
            "warning": "Insufficient autocorrelation data points or non-physical temperature."
        }

    # Average over available off-diagonal stress components
    components = [acf_pxy]
    if acf_pxz and len(acf_pxz) == n:
        components.append(acf_pxz)
    if acf_pyz and len(acf_pyz) == n:
        components.append(acf_pyz)

    m = len(components)
    acf_avg = [sum(components[c][i] for c in range(m)) / m for i in range(n)]

    # Determine integration upper limit to prevent tail noise divergence
    max_idx = int(n * max(0.1, min(1.0, upper_cutoff_fraction)))
    if max_idx < 2:
        max_idx = n

    # Composite trapezoidal integration: integral of ACF(t) dt
    integral = 0.0
    running_integral = [0.0]
    for i in range(1, max_idx):
        dt = time_pts[i] - time_pts[i - 1]
        step_val = 0.5 * (acf_avg[i - 1] + acf_avg[i]) * dt
        integral += step_val
        running_integral.append(integral)

    # Unit conversion factor to SI (Pa·s)
    # real units: P in atm (101325 Pa), V in Å³ (1e-30 m³), t in fs (1e-15 s)
    # metal units: P in bar (1e5 Pa), V in Å³ (1e-30 m³), t in ps (1e-12 s)
    # lj units: dimensionless
    if units == "real":
        v_m3 = volume * 1e-30
        p_factor = 101325.0
        t_factor = 1e-15
        prefactor = (v_m3 * (p_factor ** 2) * t_factor) / (KB_SI * temp)
        viscosity_pa_s = integral * prefactor
        viscosity_cp = viscosity_pa_s * 1000.0  # 1 Pa·s = 1000 cP
    elif units == "metal":
        v_m3 = volume * 1e-30
        p_factor = 1.0e5
        t_factor = 1e-12
        prefactor = (v_m3 * (p_factor ** 2) * t_factor) / (KB_SI * temp)
        viscosity_pa_s = integral * prefactor
        viscosity_cp = viscosity_pa_s * 1000.0
    else:  # lj reduced units
        prefactor = volume / temp
        viscosity_pa_s = integral * prefactor
        viscosity_cp = viscosity_pa_s

    return {
        "viscosity_pa_s": viscosity_pa_s,
        "viscosity_cp": viscosity_cp,
        "integrated_integral": integral,
        "components_averaged": m,
        "data_points_integrated": max_idx,
        "units": units,
        "scientific_note": (
            "Green-Kubo shear viscosity requires long trajectories (> 100 ps for atomistic liquids) "
            "with noise filtering or block-averaging to ensure the stress correlation integral reaches a stable plateau."
        )
    }
