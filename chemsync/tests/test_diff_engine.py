"""Tests for diff engine matching and comparison."""

from chemsync.engine.diff_engine import compute_diffs, summarize_diffs
from chemsync.models.chemical import ChemicalRecord, CompoundData, ContainerAssignment, ExtraFieldValue
from chemsync.models.diff import MatchStatus


def _make_record(
    title: str, cas: str | None = None, item_id: int | None = None,
    purity: str = "", supplier: str = "",
) -> ChemicalRecord:
    compound = CompoundData(name=title, cas_number=cas) if cas else None
    extra_fields = {}
    if purity:
        extra_fields["Purity"] = ExtraFieldValue(value=purity)
    if supplier:
        extra_fields["Supplier Info"] = ExtraFieldValue(value=supplier)
    return ChemicalRecord(
        title=title,
        elabftw_item_id=item_id,
        compound=compound,
        extra_fields=extra_fields,
    )


def test_new_record():
    source = [_make_record("Aceton", "67-64-1")]
    elab = []
    diffs = compute_diffs(source, elab)
    assert len(diffs) == 1
    assert diffs[0].status == MatchStatus.NEW


def test_unchanged_record():
    source = [_make_record("Aceton", "67-64-1", purity="99%")]
    elab = [_make_record("Aceton", "67-64-1", item_id=1, purity="99%")]
    diffs = compute_diffs(source, elab)
    assert any(d.status == MatchStatus.UNCHANGED for d in diffs)


def test_changed_record():
    source = [_make_record("Aceton", "67-64-1", purity="99%")]
    elab = [_make_record("Aceton", "67-64-1", item_id=1, purity="95%")]
    diffs = compute_diffs(source, elab)
    changed = [d for d in diffs if d.status == MatchStatus.CHANGED]
    assert len(changed) == 1
    assert any(f.field_name == "Purity" and f.is_different for f in changed[0].field_diffs)


def test_missing_in_source():
    source = []
    elab = [_make_record("Aceton", "67-64-1", item_id=1)]
    diffs = compute_diffs(source, elab)
    assert len(diffs) == 1
    assert diffs[0].status == MatchStatus.MISSING_IN_SOURCE


def test_duplicate_cas_disambiguation():
    """Multiple CSV rows with same CAS should match different eLabFTW items."""
    source = [
        _make_record("Silan A", "4420-74-0", supplier="Alfa Aesar, 10141877"),
        _make_record("Silan B", "4420-74-0", supplier="Alfa Aesar, 10173798"),
    ]
    elab = [
        _make_record("Silan A", "4420-74-0", item_id=1, supplier="Alfa Aesar, 10141877"),
        _make_record("Silan B", "4420-74-0", item_id=2, supplier="Alfa Aesar, 10173798"),
    ]
    diffs = compute_diffs(source, elab)
    # Both should match (not appear as NEW)
    statuses = {d.status for d in diffs}
    assert MatchStatus.NEW not in statuses


def test_summarize():
    source = [
        _make_record("New Chemical", "12345-67-8"),
        _make_record("Aceton", "67-64-1", purity="99%"),
    ]
    elab = [
        _make_record("Aceton", "67-64-1", item_id=1, purity="95%"),
        _make_record("Old Chemical", "99999-99-9", item_id=2),
    ]
    diffs = compute_diffs(source, elab)
    s = summarize_diffs(diffs)
    assert s["new"] == 1
    assert s["changed"] == 1
    assert s["missing"] == 1
