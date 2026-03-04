# ChemSync - Projekt-Uebergabe & TODOs

## Branch & Repo

```bash
git clone <your-repo-url>
git checkout claude/database-sync-assistant-K1dB0
cd chemsync
pip install -e ".[dev]"
python -m pytest tests/ -v  # 26 Tests, alle gruen
```

---

## Status: Phase 1 FERTIG

Alle Core-Module sind implementiert und getestet:

| Modul | Datei | Status |
|---|---|---|
| Datenmodelle | `chemsync/models/chemical.py`, `diff.py`, `mapping.py` | FERTIG |
| API-Client | `chemsync/api/client.py` | FERTIG |
| CSV-Reader | `chemsync/source/csv_reader.py` | FERTIG |
| Hazard-Mapper | `chemsync/engine/hazard_mapper.py` | FERTIG |
| Metadata-Builder | `chemsync/engine/metadata_builder.py` | FERTIG |
| Diff-Engine | `chemsync/engine/diff_engine.py` | FERTIG |
| Sync-Engine | `chemsync/engine/sync_engine.py` | FERTIG |
| Default-Mapping | `mappings/default_chemdb.json` | FERTIG |
| Unit Tests (26) | `tests/test_*.py` | FERTIG |

CLI funktioniert bereits:
```bash
chemsync --csv inventarliste.csv --mapping mappings/default_chemdb.json \
    --url https://elab.example.com --api-key "your-key" --dry-run
```

---

## TODO: Phase 2 - PyQt6 GUI

### Zu erstellen (7 Dateien):

**1. `chemsync/gui/__init__.py`** - existiert bereits (leer)

**2. `chemsync/gui/main_window.py`** - QMainWindow mit QTabWidget (Wizard)
- 5 Tabs: Verbindung, CSV, Mapping, Vergleich, Sync
- Navigation: Zurueck/Weiter Buttons
- Tab-Reihenfolge erzwingen (kein Sprung zu Vergleich ohne geladene Daten)

**3. `chemsync/gui/connection_panel.py`** - Screen 1
- QLineEdit fuer URL
- QLineEdit fuer API-Key (EchoMode.Password)
- QPushButton "Verbindung testen" -> ruft `client.test_connection()` auf
- QComboBox fuer Kategorie (befuellt nach erfolgreichem Test via `get_items_types()`)
- Speichern/Laden aus `~/.chemsync/config.json` (AppConfig Klasse existiert)

**4. `chemsync/gui/source_panel.py`** - Screen 2
- QPushButton "CSV oeffnen" -> QFileDialog (Filter: *.csv *.tsv *.txt)
- QComboBox fuer Delimiter (auto-detect, ueberschreibbar)
- QComboBox fuer Encoding (UTF-8, Latin-1, CP1252)
- QTableWidget fuer Vorschau (erste 10 Zeilen)
- `CsvReader.preview()` existiert bereits

**5. `chemsync/gui/mapping_panel.py`** - Screen 3
- QTableWidget mit 3 Spalten:
  - Spalte 0: CSV-Spaltenname/-index (ReadOnly)
  - Spalte 1: Ziel-Bereich (QComboBox: Item/Compound/Extra Field/Container/Storage/Ignorieren)
  - Spalte 2: Ziel-Feld (QComboBox, abhaengig vom Bereich)
- QPushButton "Profil laden" / "Profil speichern" -> MappingProfile.load()/save()
- Compound-Ziel-Felder: cas_number, molecular_formula, molecular_weight, h_statements, smiles, inchi, ec_number, pubchem_cid
- Item-Ziel-Felder: title
- Container-Ziel-Felder: qty_and_unit
- Storage-Ziel-Felder: location
- Extra Field: Freitext-Name

**6. `chemsync/gui/diff_panel.py`** - Screen 4 (Hauptscreen)
- Statuszeile oben: "23 Neu | 47 Geaendert | 912 Unveraendert | 3 Fehlt"
- QTableView mit QAbstractTableModel:
  - Spalten: [Checkbox] | Status | CAS | Name | [Feld-Paare]
  - Farbcodierung: Gruen=NEW, Gelb=CHANGED, Grau=UNCHANGED, Rot=MISSING
  - Custom Delegate fuer Zell-Faerbung
- Filter-Buttons (QButtonGroup): Alle / Nur Neue / Nur Geaenderte
- Doppelklick -> Detail-QDialog mit allen FieldDiffs
- Datenquelle: `compute_diffs()` + `summarize_diffs()` aus diff_engine

**7. `chemsync/gui/sync_panel.py`** - Screen 5
- QCheckBox "Dry-Run" (Standard: aktiviert)
- QPushButton "Sync starten"
- QProgressBar
- QTextEdit fuer Live-Log (ReadOnly, auto-scroll)
- Ergebnis-Label: "X erstellt, Y aktualisiert, Z Fehler"
- Nutzt `SyncEngine.sync_records(on_progress=...)` im Worker-Thread

**8. `chemsync/gui/workers.py`** - QThread-Wrapper
- `LoadItemsWorker(QThread)`: Laedt eLabFTW-Items im Hintergrund
- `SyncWorker(QThread)`: Fuehrt Sync aus, emittiert progress Signal
- Signals: `progress(int, int, str)`, `finished(SyncResult)`, `error(str)`

### Wichtige Hinweise fuer GUI-Implementierung:

- `pip install PyQt6` separat noetig (optional dependency)
- `__main__.py` hat bereits `--gui` Flag vorbereitet
- Alle Engine-Methoden sind synchron -> muessen in QThread laufen
- `SyncEngine.sync_records()` akzeptiert `on_progress` Callback
- `CsvReader.preview()` gibt `list[list[str]]` zurueck fuer Vorschau-Tabelle
- `MappingProfile` kann aus JSON geladen/gespeichert werden
- `AppConfig` speichert URL/Key/Kategorie in `~/.chemsync/config.json`

---

## TODO: Phase 3 - Erweiterungen (optional)

### Legacy Body-Migration
- `chemsync/migration/body_extractor.py`: HTML-Body parsen (BeautifulSoup)
- Pattern: `<p>Feldname: Wert</p>` (aus existierenden eLabFTW Items)
- CAS-Regex: `r"CAS[:\s]*(\d{2,7}-\d{2}-\d)"`
- Bei Sync: `hide_main_text=1` setzen, Body nicht loeschen (Backup)

### Excel-Support
- `openpyxl` als Dependency hinzufuegen
- `chemsync/source/excel_reader.py`: XLSX -> selbes Interface wie CsvReader

### Alte Datenbank-Anbindung
- Direkte DB-Verbindung (MySQL/PostgreSQL) zur alten ChemDB
- Eigener SourceAdapter wie CsvReader

### PubChem-Anreicherung
- Fehlende Felder (SMILES, InChI, Molmasse) via PubChem API ergaenzen
- `chemsync/engine/pubchem_client.py`: Suche nach CAS -> alle Felder zurueck

---

## Wichtige API-Details (eLabFTW 5.4.x)

### Berechtigungen (Schema 197)
```python
# canread_base und canwrite_base sind Integer-Felder, NICHT im JSON!
payload = {
    "canread_base": 30,   # Team
    "canwrite_base": 20,  # User+Admins
}
# BasePermissions: Full=50, Org=40, Team=30, User=20, UserOnly=10
```

### hide_main_text (Schema 196)
```python
# Body ausblenden nach Migration (bleibt als Backup erhalten):
PATCH /api/v2/items/{id}  {"hide_main_text": 1}
# NICHT mehr im metadata-JSON! Das alte display_main_text existiert nicht mehr.
```

### Compound-Upsert
```python
POST /api/v2/compounds {"action": "create", "name": ..., "cas_number": ...}
# Server gibt existierende ID zurueck bei Duplikat-CAS (kein Fehler)
```

### Container erstellen
```python
POST /api/v2/items/{item_id}/containers
Body: {"storage_id": 5, "qty_stored": 100.0, "qty_unit": "mL"}
# storage_id im Body, NICHT in der URL
```

---

## CSV-Format Referenz

Euer ChemDB-Export hat **kein Header**, Semikolon-getrennt, 16 Spalten:

| Pos | Inhalt | Ziel |
|---|---|---|
| 0 | Substanzname | `item.title` |
| 1 | CAS-Nr | `compound.cas_number` |
| 2 | Menge+Einheit ("100 ml") | `container` (parse_quantity) |
| 3 | Beschreibung | `extra_field.Description` |
| 4 | H-Saetze | `compound` GHS-Flags (hazard_mapper) |
| 5 | P-Saetze (mit [...]) | `extra_field.P-Statements` (strip_annotations) |
| 6 | GHS-Pictogramme | ignorieren |
| 7 | Lieferant+Charge | `extra_field.Supplier Info` |
| 8 | Lagerort | `storage.location` |
| 9 | Verantwortliche(r) | `extra_field.Responsible Person` |
| 10 | Reinheit | `extra_field.Purity` |
| 11 | GHS (Duplikat) | ignorieren |
| 12 | Molmasse ("236,34") | `compound.molecular_weight` (decimal_de) |
| 13 | Schmelz-/Siedepunkt | `extra_field.Melting/Boiling Point` |
| 14 | ? (meist leer) | ignorieren |
| 15 | Farbe/Aussehen | `extra_field.Appearance` |

Besonderheiten: Dezimalkomma, PHP-Warnings am Ende, Raum im Header-Kommentar,
gleiche CAS mehrfach (verschiedene Flaschen), H999 = keine Einstufung.

---

## Architektur-Uebersicht

```
chemsync/
|-- chemsync/
|   |-- __main__.py              # Entry point: --gui oder --csv CLI
|   |-- config.py                # AppConfig (URL, Key, Kategorie) -> ~/.chemsync/
|   |-- models/
|   |   |-- chemical.py          # ChemicalRecord, CompoundData, ExtraFieldValue, ContainerAssignment
|   |   |-- diff.py              # RecordDiff, FieldDiff, MatchStatus (NEW/CHANGED/UNCHANGED/MISSING)
|   |   |-- mapping.py           # MappingProfile, FormatConfig, ColumnMapping (JSON speicherbar)
|   |-- source/
|   |   |-- csv_reader.py        # CsvReader + parse_quantity/decimal_de/strip_p/validate_cas
|   |-- api/
|   |   |-- client.py            # ElabFtwClient (Items, Compounds, Storage, Containers)
|   |-- engine/
|   |   |-- hazard_mapper.py     # H-Saetze -> GHS Flags (mit Klammer/Suffix-Handling)
|   |   |-- metadata_builder.py  # build_metadata(), merge_metadata(), extract_extra_fields()
|   |   |-- diff_engine.py       # compute_diffs(), CAS+Supplier Matching
|   |   |-- sync_engine.py       # SyncEngine (create/update), run_cli_sync()
|   |-- gui/                     # <-- TODO Phase 2
|   |-- migration/               # <-- TODO Phase 3
|-- mappings/
|   |-- default_chemdb.json      # Euer ChemDB-Inventarlisten-Profil
|-- tests/                       # 26 Tests (pytest)
|-- pyproject.toml
```
