"""CSV reader with support for the ChemDB export format."""

from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path

from chemsync.engine.hazard_mapper import parse_h_statements
from chemsync.models.chemical import ChemicalRecord, CompoundData, ContainerAssignment, ExtraFieldValue
from chemsync.models.mapping import ColumnMapping, MappingProfile

logger = logging.getLogger(__name__)


# --- Parsing helpers ---

_UNIT_MAP = {
    "ml": "mL", "µl": "µL", "ul": "µL", "l": "L",
    "g": "g", "kg": "kg", "mg": "mg", "µg": "µg", "ug": "µg",
    "bar": "bar",
}


def normalize_unit(raw: str) -> str:
    """Normalize unit string to eLabFTW format."""
    return _UNIT_MAP.get(raw.lower().strip(), raw.strip())


def parse_quantity(raw: str) -> tuple[float, str]:
    """Parse combined quantity+unit string.

    '100 ml' -> (100.0, 'mL')
    '25 g' -> (25.0, 'g')
    '2 M' -> (2.0, 'M')
    """
    raw = raw.strip()
    if not raw:
        return 1.0, "unit"
    match = re.match(r"([\d.,]+)\s*(.+)", raw)
    if match:
        qty_str = match.group(1).replace(",", ".")
        try:
            qty = float(qty_str)
        except ValueError:
            return 1.0, "unit"
        unit = normalize_unit(match.group(2))
        return qty, unit
    return 1.0, "unit"


def parse_decimal_de(raw: str) -> float:
    """Parse German decimal format: '236,34' -> 236.34."""
    raw = raw.strip()
    if not raw:
        return 0.0
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return 0.0


def strip_p_annotations(raw: str) -> str:
    """Remove bracket annotations from P-statements.

    'P501["einer anerkannten..."]' -> 'P501'
    """
    return re.sub(r'\["[^"]*"\]', "", raw).strip()


def extract_room_from_header(lines: list[str]) -> str | None:
    """Extract room name from comment header.

    '# Inventarliste für Raum WIN-2.202' -> 'WIN-2.202'
    """
    for line in lines:
        m = re.match(r"#.*\b(?:Raum|Room)\s+(\S+)", line)
        if m:
            return m.group(1)
    return None


def validate_cas(cas: str) -> bool:
    """Validate CAS number with checksum (identical to eLabFTW CompoundParams.php:137-159)."""
    cas = cas.strip()
    match = re.match(r"^(\d{2,7})-(\d{2})-(\d)$", cas)
    if not match:
        return False
    digits = match.group(1) + match.group(2)
    checksum = int(match.group(3))
    total = sum(int(d) * (len(digits) - i) for i, d in enumerate(digits))
    return total % 10 == checksum


def _is_junk_line(line: str) -> bool:
    """Detect PHP warnings and HTML garbage at end of export."""
    stripped = line.strip()
    return bool(
        stripped.startswith("<br")
        or stripped.startswith("<b>Warning</b>")
        or stripped.startswith("<b>Notice</b>")
        or "<b>Warning</b>" in stripped
    )


# --- CSV Reader ---

class CsvReader:
    """Reads ChemDB CSV exports and converts to ChemicalRecord list."""

    def load(self, filepath: str | Path, profile: MappingProfile) -> tuple[list[ChemicalRecord], str | None]:
        """Load CSV file and apply mapping profile.

        Returns:
            Tuple of (records, room_name).
            room_name is extracted from header comments if room_from_header is True.
        """
        filepath = Path(filepath)
        fmt = profile.format

        # Read raw lines with encoding detection
        raw_text = self._read_with_encoding(filepath, fmt.encoding)
        lines = raw_text.splitlines()

        # Extract room from header comments
        room: str | None = None
        if fmt.room_from_header:
            comment_lines = [l for l in lines if l.startswith(fmt.comment_prefix)]
            room = extract_room_from_header(comment_lines)

        # Filter out comments and junk
        data_lines = [
            l for l in lines
            if l.strip() and not l.startswith(fmt.comment_prefix) and not _is_junk_line(l)
        ]

        # Parse CSV
        reader = csv.reader(io.StringIO("\n".join(data_lines)), delimiter=fmt.delimiter, quotechar='"')
        rows = list(reader)

        # Skip header row if present
        start_idx = 1 if fmt.has_header else 0

        records: list[ChemicalRecord] = []
        for row_num, row in enumerate(rows[start_idx:], start=start_idx + 1):
            record = self._row_to_record(row, row_num, profile, room)
            if record:
                records.append(record)

        logger.info("Loaded %d records from %s (room: %s)", len(records), filepath.name, room)
        return records, room

    def preview(self, filepath: str | Path, profile: MappingProfile, max_rows: int = 10) -> list[list[str]]:
        """Load first N rows for preview."""
        filepath = Path(filepath)
        fmt = profile.format
        raw_text = self._read_with_encoding(filepath, fmt.encoding)
        lines = raw_text.splitlines()

        data_lines = [
            l for l in lines
            if l.strip() and not l.startswith(fmt.comment_prefix) and not _is_junk_line(l)
        ]

        reader = csv.reader(io.StringIO("\n".join(data_lines[:max_rows])), delimiter=fmt.delimiter, quotechar='"')
        return list(reader)

    @staticmethod
    def _read_with_encoding(filepath: Path, preferred: str) -> str:
        """Try preferred encoding, fallback to latin-1."""
        for enc in (preferred, "latin-1", "cp1252"):
            try:
                return filepath.read_text(encoding=enc)
            except (UnicodeDecodeError, LookupError):
                continue
        raise ValueError(f"Cannot decode {filepath} with any supported encoding")

    def _row_to_record(
        self, row: list[str], row_num: int, profile: MappingProfile, room: str | None
    ) -> ChemicalRecord | None:
        """Convert a single CSV row to a ChemicalRecord using the mapping profile."""
        compound = CompoundData()
        extra_fields: dict[str, ExtraFieldValue] = {}
        title = ""
        qty = 1.0
        unit = "unit"
        storage_location: str | None = None
        warnings: list[str] = []
        ef_position = 0

        for col_map in profile.columns:
            if col_map.is_ignored or col_map.index >= len(row):
                continue

            raw_value = row[col_map.index].strip()
            if not raw_value:
                continue

            area = col_map.target_area
            field_name = col_map.target_field

            if area == "item":
                if field_name == "title":
                    title = raw_value

            elif area == "compound":
                self._apply_compound_field(compound, field_name, raw_value, col_map.parser, warnings)

            elif area == "extra_field":
                value = raw_value
                if col_map.parser == "strip_annotations":
                    value = strip_p_annotations(value)
                extra_fields[field_name] = ExtraFieldValue(
                    value=value, type="text", position=ef_position
                )
                ef_position += 1

            elif area == "container":
                if col_map.parser == "quantity" or field_name == "qty_and_unit":
                    qty, unit = parse_quantity(raw_value)

            elif area == "storage":
                storage_location = raw_value

        if not title:
            return None

        # Build compound name from title if not set
        if not compound.name:
            compound.name = title

        # Validate CAS
        if compound.cas_number and not validate_cas(compound.cas_number):
            warnings.append(f"Invalid CAS checksum: {compound.cas_number}")

        # Build storage path
        container: ContainerAssignment | None = None
        if storage_location or qty != 1.0:
            path = []
            if room:
                path.append(room)
            if storage_location:
                path.append(storage_location)
            container = ContainerAssignment(
                storage_path=path, qty_stored=qty, qty_unit=unit
            )

        return ChemicalRecord(
            source_id=str(row_num),
            title=title,
            compound=compound if compound.cas_number or compound.molecular_weight else None,
            extra_fields=extra_fields,
            container=container,
            warnings=warnings,
        )

    @staticmethod
    def _apply_compound_field(
        compound: CompoundData, field_name: str, raw_value: str,
        parser: str | None, warnings: list[str],
    ) -> None:
        """Apply a parsed value to the appropriate CompoundData field."""
        if field_name == "cas_number":
            compound.cas_number = raw_value
        elif field_name == "molecular_formula":
            compound.molecular_formula = raw_value
        elif field_name == "molecular_weight":
            if parser == "decimal_de":
                compound.molecular_weight = parse_decimal_de(raw_value)
            else:
                try:
                    compound.molecular_weight = float(raw_value)
                except ValueError:
                    warnings.append(f"Invalid molecular weight: {raw_value}")
        elif field_name == "h_statements":
            if parser == "hazard_mapper":
                flags = parse_h_statements(raw_value)
                for flag_name, flag_val in flags.items():
                    if flag_val:
                        setattr(compound, flag_name, True)
        elif field_name == "smiles":
            compound.smiles = raw_value
        elif field_name == "inchi":
            compound.inchi = raw_value
        elif field_name == "ec_number":
            compound.ec_number = raw_value
        elif field_name == "pubchem_cid":
            try:
                compound.pubchem_cid = int(raw_value)
            except ValueError:
                warnings.append(f"Invalid PubChem CID: {raw_value}")
