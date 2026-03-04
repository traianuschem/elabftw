"""Core data models for chemical records."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CompoundData:
    """Maps to eLabFTW compounds table."""

    name: str = ""
    cas_number: str | None = None
    molecular_formula: str | None = None
    molecular_weight: float = 0.0
    smiles: str | None = None
    inchi: str | None = None
    inchi_key: str | None = None
    iupac_name: str | None = None
    pubchem_cid: int | None = None
    ec_number: str | None = None
    chebi_id: str | None = None
    chembl_id: str | None = None
    drugbank_id: str | None = None
    dsstox_id: str | None = None
    unii: str | None = None
    # GHS Boolean-Flags
    is_corrosive: bool = False
    is_explosive: bool = False
    is_flammable: bool = False
    is_toxic: bool = False
    is_hazardous2health: bool = False
    is_hazardous2env: bool = False
    is_oxidising: bool = False
    is_gas_under_pressure: bool = False
    is_serious_health_hazard: bool = False
    is_cmr: bool = False
    is_radioactive: bool = False
    is_nano: bool = False
    is_controlled: bool = False
    is_antibiotic_precursor: bool = False
    is_drug_precursor: bool = False
    is_explosive_precursor: bool = False

    def to_api_dict(self) -> dict:
        """Convert to dict for POST /api/v2/compounds."""
        d: dict = {"action": "create"}
        if self.name:
            d["name"] = self.name
        if self.cas_number:
            d["cas_number"] = self.cas_number
        if self.molecular_formula:
            d["molecular_formula"] = self.molecular_formula
        if self.molecular_weight:
            d["molecular_weight"] = str(self.molecular_weight)
        if self.smiles:
            d["smiles"] = self.smiles
        if self.inchi:
            d["inchi"] = self.inchi
        if self.inchi_key:
            d["inchi_key"] = self.inchi_key
        if self.iupac_name:
            d["iupac_name"] = self.iupac_name
        if self.pubchem_cid:
            d["pubchem_cid"] = self.pubchem_cid
        if self.ec_number:
            d["ec_number"] = self.ec_number
        # GHS flags - only send True values
        for flag_name in self.ghs_flag_names():
            if getattr(self, flag_name):
                d[flag_name] = 1
        return d

    @staticmethod
    def ghs_flag_names() -> list[str]:
        return [
            "is_corrosive", "is_explosive", "is_flammable", "is_toxic",
            "is_hazardous2health", "is_hazardous2env", "is_oxidising",
            "is_gas_under_pressure", "is_serious_health_hazard", "is_cmr",
            "is_radioactive", "is_nano", "is_controlled",
            "is_antibiotic_precursor", "is_drug_precursor", "is_explosive_precursor",
        ]


@dataclass
class ExtraFieldValue:
    """A single extra_field entry in eLabFTW metadata JSON."""

    value: str = ""
    type: str = "text"  # text, date, url, select, number
    options: list[str] | None = None
    group_id: int | None = None
    position: int = 0

    def to_dict(self) -> dict:
        d: dict = {"type": self.type, "value": self.value, "position": self.position}
        if self.group_id is not None:
            d["group_id"] = self.group_id
        if self.options is not None:
            d["options"] = self.options
        return d


@dataclass
class ChemicalRecord:
    """Central data object representing one chemical item/bottle."""

    source_id: str | None = None  # CSV line number for traceability
    elabftw_item_id: int | None = None
    title: str = ""
    compound: CompoundData | None = None
    extra_fields: dict[str, ExtraFieldValue] = field(default_factory=dict)
    container: ContainerAssignment | None = None
    tags: list[str] = field(default_factory=list)
    hide_main_text: bool = False
    canread_base: int = 30  # Team
    canwrite_base: int = 20  # User+Admins
    # Populated during matching
    elabftw_compound_id: int | None = None
    # Validation warnings
    warnings: list[str] = field(default_factory=list)


@dataclass
class ContainerAssignment:
    """Storage location + quantity for an item."""

    storage_path: list[str] = field(default_factory=list)  # ["WIN-2.202", "Chemikalienschrank"]
    qty_stored: float = 1.0
    qty_unit: str = "unit"  # mL, L, g, kg, etc.
    storage_id: int | None = None  # resolved after storage lookup
    container_link_id: int | None = None  # existing link ID for updates
