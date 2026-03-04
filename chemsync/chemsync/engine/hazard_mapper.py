"""Maps H-statements (hazard codes) to GHS boolean flags for eLabFTW compounds."""

from __future__ import annotations

import re

# H-code ranges mapped to CompoundData boolean flags
# Based on src/Elabftw/Compound.php:66-112 (PubChem Pictogram Mapping)
_H_CODE_RANGES: list[tuple[int, int, str]] = [
    # Physical hazards
    (200, 205, "is_explosive"),
    (206, 210, "is_flammable"),       # H206-H210 flammable gases
    (220, 232, "is_flammable"),       # flammable
    (240, 242, "is_explosive"),       # unstable explosives
    (250, 262, "is_flammable"),       # pyrophoric, self-heating
    (270, 272, "is_oxidising"),
    (280, 284, "is_gas_under_pressure"),
    (290, 290, "is_corrosive"),       # corrosive to metals
    # Health hazards - acute toxicity
    (300, 302, "is_toxic"),           # fatal/toxic if swallowed
    (304, 304, "is_toxic"),           # may be fatal if swallowed and enters airways
    (310, 312, "is_toxic"),           # fatal/toxic in contact with skin
    (314, 314, "is_corrosive"),       # causes severe skin burns
    (315, 315, "is_hazardous2health"),  # skin irritation
    (317, 317, "is_hazardous2health"),  # allergic skin reaction
    (318, 318, "is_corrosive"),       # serious eye damage
    (319, 320, "is_hazardous2health"),  # eye irritation
    (330, 332, "is_toxic"),           # fatal/toxic if inhaled
    (334, 334, "is_serious_health_hazard"),  # allergy/asthma if inhaled
    (335, 336, "is_hazardous2health"),  # respiratory irritation, drowsiness
    # Health hazards - CMR and chronic
    (340, 341, "is_cmr"),             # germ cell mutagenicity
    (350, 351, "is_cmr"),             # carcinogenicity
    (360, 361, "is_cmr"),             # reproductive toxicity
    (362, 362, "is_serious_health_hazard"),  # harm to breastfed children
    (370, 373, "is_serious_health_hazard"),  # specific target organ toxicity
    # Environmental hazards
    (400, 420, "is_hazardous2env"),
]


def parse_h_statements(raw: str) -> dict[str, bool]:
    """Parse H-statement string and return GHS boolean flags.

    Input examples:
        "H225-H319-H336"
        "H225-H304-H315-H330-H336-H350-H361f-H370[\"\", \"\"]-H372[\"\", \"\"]-H411"

    Parsing steps:
        1. Remove bracket annotations: H370["", ""] -> H370
        2. Remove suffix letters: H361f -> H361
        3. Split on '-' (but not inside H-codes like H305+H351)
        4. H999 = placeholder for "no classification" -> ignore
        5. Map each H-number to GHS flags
    """
    flags: dict[str, bool] = {
        "is_corrosive": False,
        "is_explosive": False,
        "is_flammable": False,
        "is_toxic": False,
        "is_hazardous2health": False,
        "is_hazardous2env": False,
        "is_oxidising": False,
        "is_gas_under_pressure": False,
        "is_serious_health_hazard": False,
        "is_cmr": False,
        "is_radioactive": False,
        "is_nano": False,
        "is_controlled": False,
        "is_antibiotic_precursor": False,
        "is_drug_precursor": False,
        "is_explosive_precursor": False,
    }

    if not raw or not raw.strip():
        return flags

    # Step 1: Remove bracket annotations
    cleaned = re.sub(r'\[[^\]]*\]', "", raw)

    # Step 2: Extract all H-codes (H followed by digits, optionally with suffix letters)
    h_codes = re.findall(r"H(\d{3})[a-z]*", cleaned)

    for code_str in h_codes:
        code = int(code_str)
        # Step 4: Skip H999 placeholder
        if code == 999:
            continue
        # Step 5: Map to flags
        for low, high, flag_name in _H_CODE_RANGES:
            if low <= code <= high:
                flags[flag_name] = True

    return flags


def format_h_statements(flags: dict[str, bool]) -> str:
    """Reverse: get a human-readable summary of active GHS flags."""
    active = [k.replace("is_", "").replace("2", " to ").title() for k, v in flags.items() if v]
    return ", ".join(active) if active else "None"
