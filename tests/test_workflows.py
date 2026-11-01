import sys
from pathlib import Path
import tempfile
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workflows.input_generator import generate_tensile_script
from scripts.parse_dump import LammpsDumpParser


def test_generate_tensile_script_defaults():
    """Verify standard generation with default parameters."""
    script = generate_tensile_script({})
    assert "units           metal" in script
    assert "velocity        all create 300.0" in script
    assert "erate 0.01" in script
    assert "run             25000" in script


def test_generate_tensile_script_custom():
    """Verify parameterized generation with custom temperature and steps."""
    params = {
        "temperature": 600.0,
        "strain_rate": 0.005,
        "run_steps": 10000,
        "potential_file": "Custom.eam.alloy",
        "element": "Al",
    }
    script = generate_tensile_script(params)
    assert "velocity        all create 600.0" in script
    assert "erate 0.005" in script
    assert "run             10000" in script
    assert "Custom.eam.alloy Al" in script


def test_lammps_dump_parser_with_synthetic_dump():
    """Verify that LammpsDumpParser reads timestep, bounds, and atom matrices."""
    synthetic_dump = """ITEM: TIMESTEP
100
ITEM: NUMBER OF ATOMS
2
ITEM: BOX BOUNDS pp pp pp
0.0 10.0
0.0 10.0
0.0 20.0
ITEM: ATOMS id type x y z
1 1 0.5 0.5 0.5
2 1 1.5 1.5 1.5
"""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".dump") as f:
        f.write(synthetic_dump)
        tmp_name = f.name

    try:
        parser = LammpsDumpParser(tmp_name)
        snapshots = list(parser.parse_snapshots())
        assert len(snapshots) == 1

        snap = snapshots[0]
        assert snap["timestep"] == 100
        assert snap["num_atoms"] == 2
        assert snap["box_bounds"].shape == (3, 2)
        assert snap["columns"] == ["id", "type", "x", "y", "z"]
        assert snap["data"].shape == (2, 5)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def test_workflow_config_example_structure():
    """Verify that workflows/config.example.yaml exists and defines required workflow keys."""
    config_path = REPO_ROOT / "workflows" / "config.example.yaml"
    assert config_path.is_file(), "config.example.yaml should exist in workflows/"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "simulation" in config
    assert "potential" in config
    assert "equilibration" in config
    assert "tensile" in config
    assert "output" in config

    assert config["simulation"]["element"] == "Cu"
    assert config["tensile"]["strain_rate"] == 0.01
    assert config["tensile"]["run_steps"] == 25000
