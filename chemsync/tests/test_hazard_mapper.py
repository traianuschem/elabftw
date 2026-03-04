"""Tests for H-statement to GHS flag mapping."""

from chemsync.engine.hazard_mapper import parse_h_statements


def test_simple_h_codes():
    flags = parse_h_statements("H225-H319-H336")
    assert flags["is_flammable"] is True
    assert flags["is_hazardous2health"] is True  # H319
    assert flags["is_toxic"] is False


def test_complex_with_annotations():
    """Real example from ChemDB CSV."""
    raw = 'H225-H304-H315-H330-H336-H350-H361f-H370["", ""]-H372["", ""]-H411'
    flags = parse_h_statements(raw)
    assert flags["is_flammable"] is True       # H225
    assert flags["is_toxic"] is True           # H304, H330
    assert flags["is_hazardous2health"] is True  # H315
    assert flags["is_cmr"] is True             # H350, H361
    assert flags["is_serious_health_hazard"] is True  # H370, H372
    assert flags["is_hazardous2env"] is True   # H411


def test_corrosive():
    flags = parse_h_statements("H318-H412")
    assert flags["is_corrosive"] is True       # H318
    assert flags["is_hazardous2env"] is True   # H412


def test_h999_placeholder():
    """H999 is a placeholder for 'no classification'."""
    flags = parse_h_statements("H999")
    assert all(not v for v in flags.values())


def test_empty_string():
    flags = parse_h_statements("")
    assert all(not v for v in flags.values())


def test_oxidising_and_pressure():
    flags = parse_h_statements("H270-H280")
    assert flags["is_oxidising"] is True
    assert flags["is_gas_under_pressure"] is True


def test_explosive():
    flags = parse_h_statements("H242-H315-H319-H335")
    assert flags["is_explosive"] is True       # H242
    assert flags["is_hazardous2health"] is True  # H315, H319, H335
