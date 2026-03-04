"""Mapping profile model for CSV column -> eLabFTW field mapping."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FormatConfig:
    """CSV format configuration."""

    delimiter: str = ";"
    encoding: str = "utf-8"
    quoting: str = "all"
    has_header: bool = False
    comment_prefix: str = "#"
    decimal_separator: str = ","
    room_from_header: bool = True


@dataclass
class ColumnMapping:
    """Maps a CSV column index to an eLabFTW target field."""

    index: int
    target: str  # e.g. "item.title", "compound.cas_number", "extra_field.Purity", "_ignore"
    parser: str | None = None  # "quantity", "hazard_mapper", "strip_annotations", "decimal_de"

    @property
    def is_ignored(self) -> bool:
        return self.target == "_ignore"

    @property
    def target_area(self) -> str:
        """E.g. 'item', 'compound', 'extra_field', 'container', 'storage'."""
        return self.target.split(".")[0] if "." in self.target else self.target

    @property
    def target_field(self) -> str:
        """E.g. 'title', 'cas_number', 'Purity'."""
        return self.target.split(".", 1)[1] if "." in self.target else ""


@dataclass
class MappingProfile:
    """Complete mapping profile: format config + column mappings."""

    name: str = "default"
    format: FormatConfig = field(default_factory=FormatConfig)
    columns: list[ColumnMapping] = field(default_factory=list)

    def save(self, filepath: str | Path) -> None:
        data = {
            "name": self.name,
            "format": {
                "delimiter": self.format.delimiter,
                "encoding": self.format.encoding,
                "quoting": self.format.quoting,
                "has_header": self.format.has_header,
                "comment_prefix": self.format.comment_prefix,
                "decimal_separator": self.format.decimal_separator,
                "room_from_header": self.format.room_from_header,
            },
            "columns": [
                {"index": c.index, "target": c.target, **({"parser": c.parser} if c.parser else {})}
                for c in self.columns
            ],
        }
        Path(filepath).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, filepath: str | Path) -> MappingProfile:
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        fmt = FormatConfig(**data.get("format", {}))
        columns = [ColumnMapping(**c) for c in data.get("columns", [])]
        return cls(name=data.get("name", "loaded"), format=fmt, columns=columns)
