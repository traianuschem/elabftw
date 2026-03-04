"""Matching and diff engine: compares CSV records with eLabFTW items."""

from __future__ import annotations

import logging

from chemsync.engine.metadata_builder import extract_extra_fields
from chemsync.models.chemical import ChemicalRecord, CompoundData, ContainerAssignment
from chemsync.models.diff import FieldDiff, MatchStatus, RecordDiff

logger = logging.getLogger(__name__)


def build_elab_records(items: list[dict]) -> list[ChemicalRecord]:
    """Convert eLabFTW API item dicts to ChemicalRecord list."""
    records: list[ChemicalRecord] = []
    for item in items:
        compound = _extract_compound(item)
        extra_fields = extract_extra_fields(item.get("metadata"))
        container = _extract_container(item)

        rec = ChemicalRecord(
            elabftw_item_id=item["id"],
            title=item.get("title", ""),
            compound=compound,
            extra_fields=extra_fields,
            container=container,
        )
        # Store compound link ID for later
        compounds_links = item.get("compounds_links", [])
        if compounds_links:
            rec.elabftw_compound_id = compounds_links[0].get("compound_id")

        records.append(rec)
    return records


def _extract_compound(item: dict) -> CompoundData | None:
    """Extract CompoundData from item's compounds_links."""
    links = item.get("compounds_links", [])
    if not links:
        return None
    # Use the first compound link
    c = links[0]
    return CompoundData(
        name=c.get("name", ""),
        cas_number=c.get("cas_number"),
        molecular_formula=c.get("molecular_formula"),
        molecular_weight=float(c.get("molecular_weight", 0) or 0),
    )


def _extract_container(item: dict) -> ContainerAssignment | None:
    """Extract ContainerAssignment from item's containers."""
    containers = item.get("containers", [])
    if not containers:
        return None
    c = containers[0]
    return ContainerAssignment(
        storage_path=[c.get("storage_name", "")],
        qty_stored=float(c.get("qty_stored", 0) or 0),
        qty_unit=c.get("qty_unit", "unit"),
        storage_id=c.get("storage_id"),
        container_link_id=c.get("id"),
    )


def compute_diffs(
    source_records: list[ChemicalRecord],
    elab_records: list[ChemicalRecord],
) -> list[RecordDiff]:
    """Match source (CSV) records against eLabFTW records and compute diffs.

    Matching strategy:
    1. Primary: CAS + Supplier Info (for duplicate CAS disambiguation)
    2. Fallback: CAS + title (exact)
    3. Fallback: title similarity
    """
    # Build index of eLabFTW records by CAS
    elab_by_cas: dict[str, list[ChemicalRecord]] = {}
    elab_by_title: dict[str, ChemicalRecord] = {}
    matched_elab_ids: set[int] = set()

    for rec in elab_records:
        if rec.compound and rec.compound.cas_number:
            elab_by_cas.setdefault(rec.compound.cas_number, []).append(rec)
        if rec.title:
            elab_by_title[rec.title.lower().strip()] = rec

    diffs: list[RecordDiff] = []

    for src in source_records:
        cas = src.compound.cas_number if src.compound else None
        match = _find_match(src, cas, elab_by_cas, elab_by_title, matched_elab_ids)

        if match is None:
            diffs.append(RecordDiff(status=MatchStatus.NEW, source_record=src))
        else:
            if match.elabftw_item_id:
                matched_elab_ids.add(match.elabftw_item_id)
            field_diffs = _compute_field_diffs(src, match)
            status = MatchStatus.CHANGED if any(d.is_different for d in field_diffs) else MatchStatus.UNCHANGED
            diffs.append(RecordDiff(
                status=status,
                source_record=src,
                target_record=match,
                field_diffs=field_diffs,
            ))

    # Add MISSING_IN_SOURCE for unmatched eLabFTW records
    for rec in elab_records:
        if rec.elabftw_item_id and rec.elabftw_item_id not in matched_elab_ids:
            diffs.append(RecordDiff(status=MatchStatus.MISSING_IN_SOURCE, target_record=rec))

    # Sort: NEW first, then CHANGED, then UNCHANGED, then MISSING
    order = {MatchStatus.NEW: 0, MatchStatus.CHANGED: 1, MatchStatus.UNCHANGED: 2, MatchStatus.MISSING_IN_SOURCE: 3}
    diffs.sort(key=lambda d: order.get(d.status, 99))

    logger.info(
        "Diff result: %d new, %d changed, %d unchanged, %d missing",
        sum(1 for d in diffs if d.status == MatchStatus.NEW),
        sum(1 for d in diffs if d.status == MatchStatus.CHANGED),
        sum(1 for d in diffs if d.status == MatchStatus.UNCHANGED),
        sum(1 for d in diffs if d.status == MatchStatus.MISSING_IN_SOURCE),
    )

    return diffs


def _find_match(
    src: ChemicalRecord,
    cas: str | None,
    elab_by_cas: dict[str, list[ChemicalRecord]],
    elab_by_title: dict[str, ChemicalRecord],
    already_matched: set[int],
) -> ChemicalRecord | None:
    """Find the best matching eLabFTW record for a source record."""
    # Strategy 1: CAS match
    if cas and cas in elab_by_cas:
        candidates = [
            r for r in elab_by_cas[cas]
            if r.elabftw_item_id not in already_matched
        ]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            # Disambiguate by supplier info
            src_supplier = _get_supplier_info(src)
            for c in candidates:
                if src_supplier and _get_supplier_info(c) == src_supplier:
                    return c
            # Fallback: match by title
            for c in candidates:
                if c.title.lower().strip() == src.title.lower().strip():
                    return c
            # Last resort: first unmatched
            return candidates[0]

    # Strategy 2: Title match
    title_key = src.title.lower().strip()
    if title_key in elab_by_title:
        candidate = elab_by_title[title_key]
        if candidate.elabftw_item_id not in already_matched:
            return candidate

    return None


def _get_supplier_info(rec: ChemicalRecord) -> str:
    """Get supplier info extra field value for disambiguation."""
    ef = rec.extra_fields.get("Supplier Info")
    return ef.value.lower().strip() if ef else ""


def _compute_field_diffs(src: ChemicalRecord, target: ChemicalRecord) -> list[FieldDiff]:
    """Compute field-level differences between source and target records."""
    diffs: list[FieldDiff] = []

    # Title
    diffs.append(FieldDiff(
        field_name="title", area="item",
        source_value=src.title, target_value=target.title,
    ))

    # Compound fields
    if src.compound and target.compound:
        for attr in ("cas_number", "molecular_formula", "molecular_weight"):
            sv = str(getattr(src.compound, attr, "") or "")
            tv = str(getattr(target.compound, attr, "") or "")
            if attr == "molecular_weight":
                # Compare floats with tolerance
                try:
                    if abs(float(sv or 0) - float(tv or 0)) < 0.01:
                        sv = tv  # treat as equal
                except ValueError:
                    pass
            diffs.append(FieldDiff(field_name=attr, area="compound", source_value=sv, target_value=tv))
    elif src.compound:
        for attr in ("cas_number", "molecular_formula", "molecular_weight"):
            sv = str(getattr(src.compound, attr, "") or "")
            diffs.append(FieldDiff(field_name=attr, area="compound", source_value=sv, target_value=""))

    # Extra fields
    all_ef_names = set(src.extra_fields.keys()) | set(target.extra_fields.keys())
    for name in sorted(all_ef_names):
        sv = src.extra_fields.get(name)
        tv = target.extra_fields.get(name)
        diffs.append(FieldDiff(
            field_name=name, area="extra_field",
            source_value=sv.value if sv else "",
            target_value=tv.value if tv else "",
        ))

    # Container
    if src.container or target.container:
        sc = src.container
        tc = target.container
        diffs.append(FieldDiff(
            field_name="qty_stored", area="container",
            source_value=str(sc.qty_stored) if sc else "",
            target_value=str(tc.qty_stored) if tc else "",
        ))
        diffs.append(FieldDiff(
            field_name="qty_unit", area="container",
            source_value=sc.qty_unit if sc else "",
            target_value=tc.qty_unit if tc else "",
        ))

    return diffs


def summarize_diffs(diffs: list[RecordDiff]) -> dict[str, int]:
    """Return count by status."""
    return {
        "new": sum(1 for d in diffs if d.status == MatchStatus.NEW),
        "changed": sum(1 for d in diffs if d.status == MatchStatus.CHANGED),
        "unchanged": sum(1 for d in diffs if d.status == MatchStatus.UNCHANGED),
        "missing": sum(1 for d in diffs if d.status == MatchStatus.MISSING_IN_SOURCE),
    }
