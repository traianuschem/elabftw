"""Diff and matching models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from chemsync.models.chemical import ChemicalRecord


class MatchStatus(Enum):
    NEW = "new"  # Only in CSV, not in eLabFTW
    CHANGED = "changed"  # Matched but fields differ
    UNCHANGED = "unchanged"  # Matched, all fields identical
    MISSING_IN_SOURCE = "missing_in_source"  # Only in eLabFTW


@dataclass
class FieldDiff:
    """Difference for a single field."""

    field_name: str
    source_value: str  # Value from CSV
    target_value: str  # Value in eLabFTW
    area: str = ""  # "compound", "extra_field", "container", "item"

    @property
    def is_different(self) -> bool:
        return self.source_value != self.target_value


@dataclass
class RecordDiff:
    """Comparison result for one chemical record."""

    status: MatchStatus
    source_record: ChemicalRecord | None = None  # From CSV
    target_record: ChemicalRecord | None = None  # From eLabFTW
    field_diffs: list[FieldDiff] = field(default_factory=list)
    selected: bool = True  # User selection for sync

    @property
    def cas(self) -> str | None:
        rec = self.source_record or self.target_record
        if rec and rec.compound:
            return rec.compound.cas_number
        return None

    @property
    def display_name(self) -> str:
        rec = self.source_record or self.target_record
        return rec.title if rec else "(unknown)"

    @property
    def changed_field_count(self) -> int:
        return sum(1 for d in self.field_diffs if d.is_different)
