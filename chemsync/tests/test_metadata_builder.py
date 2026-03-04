"""Tests for metadata JSON builder."""

import json

from chemsync.engine.metadata_builder import build_metadata, extract_extra_fields, merge_metadata
from chemsync.models.chemical import ChemicalRecord, ExtraFieldValue


def test_build_metadata():
    record = ChemicalRecord(
        title="Test",
        extra_fields={
            "Purity": ExtraFieldValue(value="95%", position=0),
            "P-Statements": ExtraFieldValue(value="P210-P233", position=1),
        },
    )
    result = json.loads(build_metadata(record))

    assert "extra_fields" in result
    assert result["extra_fields"]["Purity"]["value"] == "95%"
    assert result["extra_fields"]["Purity"]["type"] == "text"
    assert result["extra_fields"]["P-Statements"]["group_id"] == 2  # Safety group
    assert result["extra_fields"]["Purity"]["group_id"] == 1  # Properties group
    assert "elabftw" in result
    assert len(result["elabftw"]["extra_fields_groups"]) == 2


def test_extract_extra_fields():
    metadata = json.dumps({
        "extra_fields": {
            "Purity": {"type": "text", "value": "95%", "position": 0, "group_id": 1},
            "Color": {"type": "text", "value": "clear", "position": 1},
        }
    })
    fields = extract_extra_fields(metadata)
    assert "Purity" in fields
    assert fields["Purity"].value == "95%"
    assert fields["Color"].value == "clear"


def test_extract_extra_fields_empty():
    assert extract_extra_fields(None) == {}
    assert extract_extra_fields("") == {}
    assert extract_extra_fields("invalid json") == {}


def test_merge_metadata():
    existing = json.dumps({
        "extra_fields": {
            "Existing Field": {"type": "text", "value": "keep me", "position": 0},
        },
        "elabftw": {
            "extra_fields_groups": [{"id": 1, "name": "Old Group"}],
        },
    })
    record = ChemicalRecord(
        title="Test",
        extra_fields={
            "Purity": ExtraFieldValue(value="99%", position=1),
        },
    )
    result = json.loads(merge_metadata(existing, record))

    # Existing field preserved
    assert result["extra_fields"]["Existing Field"]["value"] == "keep me"
    # New field added
    assert result["extra_fields"]["Purity"]["value"] == "99%"
    # Groups preserved
    assert result["elabftw"]["extra_fields_groups"][0]["name"] == "Old Group"
