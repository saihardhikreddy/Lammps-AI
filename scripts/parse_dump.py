"""
LAMMPS Trajectory Parser

Parses atomic coordinates, box boundaries, velocities, and per-atom properties
from standard LAMMPS custom dump files into structured NumPy arrays.
"""

from typing import Dict, Generator, List, Any
import numpy as np


class LammpsDumpParser:
    """Stream parser for LAMMPS custom dump trajectory files."""

    def __init__(self, filepath: str):
        self.filepath = filepath

    def parse_snapshots(self) -> Generator[Dict[str, Any], None, None]:
        """Yields each simulation snapshot/timestep sequentially."""
        with open(self.filepath, "r") as f:
            while True:
                line = f.readline()
                if not line:
                    break

                if "ITEM: TIMESTEP" in line:
                    timestep = int(f.readline().strip())

                    # Read number of atoms
                    f.readline()  # ITEM: NUMBER OF ATOMS
                    num_atoms = int(f.readline().strip())

                    # Read box bounds
                    f.readline()  # ITEM: BOX BOUNDS
                    box_bounds = []
                    for _ in range(3):
                        bounds = [float(x) for x in f.readline().strip().split()]
                        box_bounds.append(bounds)
                    box_bounds = np.array(box_bounds)

                    # Read atom header columns
                    item_atoms = f.readline().strip()  # ITEM: ATOMS id type x y z ...
                    columns = item_atoms.split()[2:]

                    # Read atom rows
                    atom_data = []
                    for _ in range(num_atoms):
                        atom_data.append([float(x) for x in f.readline().strip().split()])

                    atom_matrix = np.array(atom_data)

                    yield {
                        "timestep": timestep,
                        "num_atoms": num_atoms,
                        "box_bounds": box_bounds,
                        "columns": columns,
                        "data": atom_matrix,
                    }


if __name__ == "__main__":
    print("LAMMPS Dump Parser module ready.")
