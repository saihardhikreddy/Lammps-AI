"""Incremental Trajectory Parser for LAMMPS dump.lammpstrj files."""
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional


class AtomRecord(list):
    """List [id, type, x, y, z, ke, von_mises_stress] with dict-like key access for backwards compatibility.

    Serializes to standard JSON array [id, type, x, y, z, ke, von_mises_stress] via json.dumps.
    """
    _KEY_MAP = {
        "id": 0,
        "type": 1,
        "x": 2,
        "y": 3,
        "z": 4,
        "ke": 5,
        "c_atomke": 5,
        "von_mises_stress": 6,
        "v_vonmises": 6,
    }

    def __getitem__(self, key):
        if isinstance(key, str):
            idx = self._KEY_MAP.get(key.lower())
            if idx is not None:
                return super().__getitem__(idx)
            raise KeyError(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self[0],
            "type": self[1],
            "x": self[2],
            "y": self[3],
            "z": self[4],
            "ke": self[5] if len(self) > 5 else None,
            "von_mises_stress": self[6] if len(self) > 6 else None,
        }


def parse_dump_frames(file_path: Path, byte_offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """Incrementally parses completed frames from a LAMMPS dump file.

    Withholds incomplete frames that are still being written by LAMMPS or the MD engine.

    Args:
        file_path: Path to the dump.lammpstrj file.
        byte_offset: Starting byte position to read from.

    Returns:
        A tuple of (frames, updated_byte_offset).
    """
    if not file_path.exists():
        return [], byte_offset

    frames = []
    current_offset = byte_offset

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(current_offset)

            frame_start_pos = current_offset
            while True:
                line = f.readline()
                if not line:
                    break

                if line.startswith("ITEM: TIMESTEP"):
                    frame_start_pos = f.tell() - len(line.encode("utf-8"))

                    # Read timestep
                    ts_line = f.readline()
                    if not ts_line:
                        f.seek(frame_start_pos)
                        break
                    try:
                        timestep = int(ts_line.strip())
                    except ValueError:
                        f.seek(frame_start_pos)
                        break

                    # ITEM: NUMBER OF ATOMS
                    natoms_header = f.readline()
                    if not natoms_header or not natoms_header.startswith("ITEM: NUMBER OF ATOMS"):
                        f.seek(frame_start_pos)
                        break
                    natoms_line = f.readline()
                    if not natoms_line:
                        f.seek(frame_start_pos)
                        break
                    try:
                        natoms = int(natoms_line.strip())
                    except ValueError:
                        f.seek(frame_start_pos)
                        break

                    # ITEM: BOX BOUNDS
                    box_header = f.readline()
                    if not box_header or not box_header.startswith("ITEM: BOX BOUNDS"):
                        f.seek(frame_start_pos)
                        break
                    box = []
                    box_complete = True
                    for _ in range(3):
                        bline = f.readline()
                        if not bline:
                            box_complete = False
                            break
                        parts = bline.strip().split()
                        if len(parts) >= 2:
                            try:
                                box.append([float(parts[0]), float(parts[1])])
                            except ValueError:
                                box_complete = False
                                break
                        else:
                            box_complete = False
                            break
                    if not box_complete or len(box) != 3:
                        f.seek(frame_start_pos)
                        break

                    # ITEM: ATOMS id type x y z ...
                    atoms_header = f.readline()
                    if not atoms_header or not atoms_header.startswith("ITEM: ATOMS"):
                        f.seek(frame_start_pos)
                        break
                    raw_col_names = atoms_header.strip().split()[2:]
                    col_names = raw_col_names if raw_col_names else ["id", "type", "x", "y", "z"]

                    # Map column names (case-insensitive) to column indices
                    col_idx = {name.lower(): idx for idx, name in enumerate(col_names)}

                    id_idx = col_idx.get("id", 0)
                    type_idx = col_idx.get("type", 1)

                    # Position columns
                    x_idx = col_idx.get("x", col_idx.get("xs", col_idx.get("xu", 2)))
                    y_idx = col_idx.get("y", col_idx.get("ys", col_idx.get("yu", 3)))
                    z_idx = col_idx.get("z", col_idx.get("zs", col_idx.get("zu", 4)))

                    # Kinetic energy column
                    ke_idx = None
                    for candidate in ("c_atomke", "atomke", "ke", "c_ke", "ke/atom"):
                        if candidate in col_idx:
                            ke_idx = col_idx[candidate]
                            break

                    # Von Mises stress column
                    stress_idx = None
                    for candidate in ("v_vonmises", "vonmises", "stress", "v_stress", "c_atomstress"):
                        if candidate in col_idx:
                            stress_idx = col_idx[candidate]
                            break

                    # Read all declared atoms
                    atoms = []
                    atoms_complete = True
                    min_required_cols = max([i for i in (id_idx, type_idx, x_idx, y_idx, z_idx) if i is not None] + [0]) + 1
                    for a_i in range(natoms):
                        aline = f.readline()
                        if not aline:
                            atoms_complete = False
                            break
                        parts = aline.strip().split()
                        if len(parts) < min_required_cols:
                            atoms_complete = False
                            break
                        try:
                            atom_id = int(parts[id_idx]) if id_idx < len(parts) else (a_i + 1)
                            atom_type = int(parts[type_idx]) if type_idx < len(parts) else 1
                            x = float(parts[x_idx]) if x_idx < len(parts) else 0.0
                            y = float(parts[y_idx]) if y_idx < len(parts) else 0.0
                            z = float(parts[z_idx]) if z_idx < len(parts) else 0.0

                            ke_val = float(parts[ke_idx]) if (ke_idx is not None and ke_idx < len(parts)) else None
                            stress_val = float(parts[stress_idx]) if (stress_idx is not None and stress_idx < len(parts)) else None

                            atoms.append(AtomRecord([atom_id, atom_type, x, y, z, ke_val, stress_val]))
                        except (ValueError, IndexError):
                            atoms_complete = False
                            break

                    if not atoms_complete or len(atoms) != natoms:
                        # Withhold incomplete frame; seek back to frame start
                        f.seek(frame_start_pos)
                        break

                    has_ke = any(a[5] is not None for a in atoms)
                    has_stress = any(a[6] is not None for a in atoms)

                    # Frame is fully validated
                    frames.append({
                        "timestep": timestep,
                        "natoms": natoms,
                        "box": box,
                        "columns": ["id", "type", "x", "y", "z", "ke", "von_mises_stress"],
                        "has_ke": has_ke,
                        "has_stress": has_stress,
                        "atoms": atoms
                    })
                    current_offset = f.tell()
                    frame_start_pos = current_offset

    except Exception:
        pass

    return frames, current_offset

