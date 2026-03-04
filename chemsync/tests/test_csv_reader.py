"""Tests for CSV reader and parsing helpers."""

import tempfile
from pathlib import Path

from chemsync.models.mapping import MappingProfile
from chemsync.source.csv_reader import (
    CsvReader,
    extract_room_from_header,
    normalize_unit,
    parse_decimal_de,
    parse_quantity,
    strip_p_annotations,
    validate_cas,
)


def test_validate_cas_valid():
    assert validate_cas("67-64-1") is True    # Acetone
    assert validate_cas("2530-83-8") is True
    assert validate_cas("4420-74-0") is True
    assert validate_cas("18107-18-1") is True


def test_validate_cas_invalid():
    assert validate_cas("67-64-2") is False   # Wrong checksum
    assert validate_cas("abc") is False
    assert validate_cas("") is False


def test_parse_quantity():
    assert parse_quantity("100 ml") == (100.0, "mL")
    assert parse_quantity("25 g") == (25.0, "g")
    assert parse_quantity("5 ml") == (5.0, "mL")
    assert parse_quantity("2 M") == (2.0, "M")
    assert parse_quantity("") == (1.0, "unit")


def test_parse_decimal_de():
    assert parse_decimal_de("236,34") == 236.34
    assert parse_decimal_de("114,22") == 114.22
    assert parse_decimal_de("") == 0.0
    assert parse_decimal_de("244.34") == 244.34  # Also handles dots


def test_strip_p_annotations():
    assert strip_p_annotations('P501["einer anerkannten Abfallentsorgungsanlage"]') == "P501"
    assert strip_p_annotations('P264["Hände"]-P273') == "P264-P273"
    assert strip_p_annotations("P210-P233") == "P210-P233"


def test_extract_room_from_header():
    lines = ["# Inventarliste für Raum WIN-2.202", "# Stand: 04.03.2026"]
    assert extract_room_from_header(lines) == "WIN-2.202"
    assert extract_room_from_header(["# no room info"]) is None


def test_normalize_unit():
    assert normalize_unit("ml") == "mL"
    assert normalize_unit("ML") == "mL"
    assert normalize_unit("g") == "g"
    assert normalize_unit("kg") == "kg"


def test_csv_reader_full():
    """Test loading a real CSV sample with the default mapping profile."""
    csv_content = (
        '# Inventarliste für Raum WIN-2.202\n'
        '# Stand: 04.03.2026\n'
        '"(3-Glycidoxipropyl)trimethoxysilan";"2530-83-8";"100 ml";"braune Flasche, roter Deckel";'
        '"H318-H412";"P273-P280-P305+P351+P338-P501[\\"einer anerkannten Abfallentsorgungsanlage\\"]";'
        '"GHS05";"";"Chemikalienschrank";"Vincent Schildknecht";"";"GHS05";"236,34";"";"";""'
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        f.flush()
        csv_path = f.name

    profile = MappingProfile.load(
        Path(__file__).parent.parent / "mappings" / "default_chemdb.json"
    )

    reader = CsvReader()
    records, room = reader.load(csv_path, profile)

    assert room == "WIN-2.202"
    assert len(records) == 1

    rec = records[0]
    assert rec.title == "(3-Glycidoxipropyl)trimethoxysilan"
    assert rec.compound is not None
    assert rec.compound.cas_number == "2530-83-8"
    assert rec.compound.molecular_weight == 236.34
    assert rec.compound.is_corrosive is True   # H318
    assert rec.compound.is_hazardous2env is True  # H412
    assert rec.container is not None
    assert rec.container.qty_stored == 100.0
    assert rec.container.qty_unit == "mL"
    assert rec.container.storage_path == ["WIN-2.202", "Chemikalienschrank"]
    assert rec.extra_fields["Responsible Person"].value == "Vincent Schildknecht"

    Path(csv_path).unlink()


def test_csv_reader_filters_php_warnings():
    """PHP warnings at end of CSV export should be filtered."""
    csv_content = (
        '"Aceton";"67-64-1";"500 ml";"";"";"";"";"";"";"";"";"";"";"";"";""\n'
        '<br />\n'
        '<b>Warning</b>:  Undefined array key "Zersetzungspunkt" in <b>/test.php</b> on line <b>52</b><br />\n'
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        f.flush()
        csv_path = f.name

    profile = MappingProfile.load(
        Path(__file__).parent.parent / "mappings" / "default_chemdb.json"
    )

    reader = CsvReader()
    records, _ = reader.load(csv_path, profile)

    assert len(records) == 1
    assert records[0].title == "Aceton"

    Path(csv_path).unlink()
