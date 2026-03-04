"""Builds eLabFTW metadata JSON from ChemicalRecord extra_fields."""

from __future__ import annotations

import json

from chemsync.models.chemical import ChemicalRecord, ExtraFieldValue


# Default extra_fields groups
DEFAULT_GROUPS = [
    {"id": 1, "name": "Properties"},
    {"id": 2, "name": "Safety"},
]

# Fields that belong to Safety group by default
_SAFETY_FIELDS = {"P-Statements", "Melting/Boiling Point", "Storage class"}


def build_metadata(record: ChemicalRecord, groups: list[dict] | None = None) -> str:
    """Build eLabFTW metadata JSON string from a ChemicalRecord.

    Returns a JSON string suitable for the 'metadata' field in API requests.
    """
    if groups is None:
        groups = DEFAULT_GROUPS

    extra_fields: dict = {}
    for name, ef in record.extra_fields.items():
        # Auto-assign group_id if not set
        if ef.group_id is None:
            ef.group_id = 2 if name in _SAFETY_FIELDS else 1
        extra_fields[name] = ef.to_dict()

    metadata = {
        "extra_fields": extra_fields,
        "elabftw": {
            "extra_fields_groups": groups,
        },
    }

    return json.dumps(metadata, ensure_ascii=False)


def merge_metadata(existing_json: str | None, record: ChemicalRecord) -> str:
    """Merge new extra_fields into existing metadata, preserving unknown keys.

    Used when updating an existing item - we don't want to overwrite
    extra_fields that weren't in the CSV.
    """
    existing: dict = {}
    if existing_json:
        try:
            existing = json.loads(existing_json)
        except json.JSONDecodeError:
            existing = {}

    existing_ef = existing.get("extra_fields", {})
    existing_elabftw = existing.get("elabftw", {})

    # Update/add fields from record
    for name, ef in record.extra_fields.items():
        if ef.group_id is None:
            ef.group_id = 2 if name in _SAFETY_FIELDS else 1
        existing_ef[name] = ef.to_dict()

    # Ensure groups exist
    if "extra_fields_groups" not in existing_elabftw:
        existing_elabftw["extra_fields_groups"] = DEFAULT_GROUPS

    existing["extra_fields"] = existing_ef
    existing["elabftw"] = existing_elabftw

    return json.dumps(existing, ensure_ascii=False)


def extract_extra_fields(metadata_json: str | None) -> dict[str, ExtraFieldValue]:
    """Extract ExtraFieldValue dict from an eLabFTW item's metadata JSON."""
    if not metadata_json:
        return {}
    try:
        metadata = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}

    result: dict[str, ExtraFieldValue] = {}
    for name, field_data in metadata.get("extra_fields", {}).items():
        if isinstance(field_data, dict):
            result[name] = ExtraFieldValue(
                value=str(field_data.get("value", "")),
                type=field_data.get("type", "text"),
                options=field_data.get("options"),
                group_id=field_data.get("group_id"),
                position=field_data.get("position", 0),
            )
    return result
