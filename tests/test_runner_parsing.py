"""The synthetic runner reads its thermostat temperatures from the script."""
from app.lammps.runner import thermostat_temps


def test_temps_come_after_the_temp_keyword_not_the_fix_id():
    assert thermostat_temps("fix 1 all nvt temp 300.0 300.0 0.1") == (300.0, 300.0)
    assert thermostat_temps("fix 2 all npt temp 1200 300 0.1 iso 0 0 1") == (1200.0, 300.0)
    assert thermostat_temps("fix nvt1 all nvt TEMP 1.5 1.0 0.5") == (1.5, 1.0)


def test_unparseable_thermostat_is_ignored():
    assert thermostat_temps("fix 1 all nvt temp ${T} ${T} 0.1") is None
    assert thermostat_temps("fix 1 all nvt temp") is None
