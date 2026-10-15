"""First-Class Molecular Self-Diffusion Module for Liquid-State MD.

Computes self-diffusion coefficients from Mean Squared Displacement (MSD)
using the Einstein relation:
    D = lim_{t -> inf} <|r(t) - r(0)|^2> / (6t)

This module operates independently with zero external dependencies.
"""
from typing import List, Dict, Any, Optional


def calculate_diffusion_coefficient(
    time_ps: List[float],
    msd_angstrom2: List[float],
    fit_start_fraction: float = 0.4
) -> Dict[str, float]:
    """Calculate the self-diffusion coefficient (D) from MSD time-series data.
    
    Parameters:
        time_ps: Simulation time points in picoseconds (ps).
        msd_angstrom2: Mean squared displacement in square angstroms (Å²).
        fit_start_fraction: Fraction of initial data to discard (skips ballistic regime, defaults to 0.4).
        
    Returns:
        Dictionary containing:
        - slope_angstrom2_ps: Linear regression slope d(MSD)/dt (Å²/ps)
        - diffusion_coefficient_m2_s: Self-diffusion coefficient D in m²/s
        - diffusion_coefficient_cm2_s: Self-diffusion coefficient D in cm²/s
        - r_squared: Coefficient of determination (R²) assessing linearity
    """
    if len(time_ps) < 2 or len(msd_angstrom2) < 2 or len(time_ps) != len(msd_angstrom2):
        return {
            "slope_angstrom2_ps": 0.0,
            "diffusion_coefficient_m2_s": 0.0,
            "diffusion_coefficient_cm2_s": 0.0,
            "r_squared": 0.0
        }

    start_idx = int(len(time_ps) * fit_start_fraction)
    # Ensure at least 2 points remain for linear regression
    if start_idx >= len(time_ps) - 1:
        start_idx = max(0, len(time_ps) - 2)

    x = time_ps[start_idx:]
    y = msd_angstrom2[start_idx:]
    n = len(x)

    sum_x = sum(x)
    sum_y = sum(y)
    sum_xx = sum(xi * xi for xi in x)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))

    denom = (n * sum_xx - sum_x * sum_x)
    if denom == 0:
        return {
            "slope_angstrom2_ps": 0.0,
            "diffusion_coefficient_m2_s": 0.0,
            "diffusion_coefficient_cm2_s": 0.0,
            "r_squared": 0.0
        }

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # Compute R^2 goodness of fit
    y_mean = sum_y / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0

    # Einstein relation in 3D: D = slope / 6
    # Units conversion: 1 Å²/ps = 1e-20 m² / 1e-12 s = 1e-8 m²/s
    D_m2_s = (slope / 6.0) * 1e-8
    D_cm2_s = D_m2_s * 1e4

    return {
        "slope_angstrom2_ps": slope,
        "diffusion_coefficient_m2_s": D_m2_s,
        "diffusion_coefficient_cm2_s": D_cm2_s,
        "r_squared": max(0.0, min(1.0, r_squared))
    }


def generate_msd_commands(
    group: str = "all",
    compute_id: str = "cMSD",
    fix_id: str = "fMSD",
    sample_every: int = 10,
    output_file: str = "msd.out"
) -> str:
    """Generate official LAMMPS command blocks for tracking 3D MSD."""
    return f"""# Compute Mean Squared Displacement (MSD)
compute         {compute_id} {group} msd
fix             {fix_id} {group} ave/time {sample_every} 1 {sample_every} c_{compute_id}[4] file {output_file} title1 "# Time MSD_total"
"""
