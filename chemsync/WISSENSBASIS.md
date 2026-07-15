# ChemSync — Wissensbasis für die Weiterentwicklung

Übergabedokument für die Migration der Chemikalien-Inventardaten (bisher CSV-Export
aus proprietärer Chemikalien-Datenbank, ~1000+ Einträge) nach eLabFTW. Fokus: technische
Grundlagen, nicht Code-Dokumentation. Eine separate Datei `HANDOVER.md` beschreibt den
konkreten Implementierungsstand des Python-Prototyps ("ChemSync").

---

## 1. Erster Schritt: Eignung von elAPI prüfen

Bevor hier weitergebaut wird, sollte geprüft werden, ob **[elAPI](https://github.com/uhd-urz/elAPI)**
(Uni Heidelberg, URZ) einen Teil der Arbeit bereits abdeckt oder als Basis taugt.

**Was elAPI ist:**
- CLI-Tool + Python-Bibliothek für die eLabFTW REST-API v2 (kompatibel mit eLabFTW 5.1.1–5.5.13)
- Unterstützt GET/POST/PATCH/DELETE auf allen API-Ressourcen, inkl. Format-Konvertierung (JSON, YAML, CSV, PDF)
- Export von Listen (z. B. alle Items) direkt nach CSV/JSON
- Plugin-Architektur (`~/.local/share/elapi/plugins/`) — eigene Kommandos ergänzbar
- Konfiguration über `elapi.yml` (Host + API-Token)
- Es existiert bereits ein Community-Plugin für Bulk-Import/Export (Desktop-App, aus CRC 1638)

**Was elAPI nicht mitbringt (Stand der Recherche):**
- Kein CSV-**Import** mit Feld-Mapping — nur generischer Export/GET/POST/PATCH
- Keine Diff/Vergleichslogik zwischen externer Quelle und bestehenden eLabFTW-Daten
- Kein Konzept für die fachspezifischen Aufgaben hier: CAS-Matching, H-Satz→GHS-Flag-Mapping,
  Storage-Pfad-Auflösung, Container-Zuordnung

**Empfehlung für den Einstieg:** elAPI als Bibliothek für die reine API-Kommunikation
(Auth, Rate-Limiting, Ressourcen-Endpunkte) evaluieren, statt einen eigenen API-Client zu pflegen.
Die fachliche Logik (CSV-Parsing, Mapping, Diff, Hazard-Mapping) müsste in jedem Fall
eigenständig entwickelt werden — das ist unabhängig von elAPI. Falls elAPI die Kernanforderungen
(Idempotenz bei Compound-Erstellung, Schema-197-Permission-Felder, Container-Endpunkte) sauber
abbildet, lässt sich der aktuelle `api/client.py`-Prototyp ggf. dadurch ersetzen oder darauf aufbauen.

---

## 2. Ausgangslage

- Aktuell liegen alle Chemikaliendaten in eLabFTW als **unstrukturiertes HTML im `body`-Feld**
  der Items — `metadata` ist leer (`null`).
- Ziel: Daten in eLabFTWs strukturierte Modelle überführen:
  - `compounds` (CAS-Nummer, Summenformel, Molmasse, 16 GHS-Gefahren-Flags, SMILES, InChI, …)
  - `metadata.extra_fields` (JSON, freie Zusatzfelder mit Gruppen)
  - `storage_units` (hierarchische Lagerorte, z. B. Raum → Schrank)
  - `containers2items` (Gebinde/Behälter mit Menge + Einheit)
- Datenquelle vorerst nur CSV-Export der alten Datenbank (kein Live-DB-Zugriff geplant).

---

## 3. eLabFTW-Datenmodell — die wichtigsten Fakten

### Compounds
- Tabelle mit 50+ Feldern, darunter 16 boolesche GHS-Gefahren-Flags
  (`is_flammable`, `is_toxic`, `is_corrosive`, `is_hazardous2health`, `is_hazardous2env`,
  `is_cmr`, `is_serious_health_hazard`, `is_oxidising`, `is_gas_under_pressure`,
  `is_explosive`, …)
- **Erstellung ist serverseitiges Upsert**: `POST /api/v2/compounds` mit `action: "create"`
  liefert bei bereits vorhandener CAS-Nummer die **existierende** ID zurück (kein Fehler,
  kein Duplikat). Das macht wiederholte Syncs idempotent.
- Verknüpfung Item ↔ Compound sowie Container ↔ Compound läuft über `INSERT IGNORE`
  auf Server-Seite → auch hier ist Mehrfachausführung ungefährlich.

### Extra Fields / Metadata
- `metadata` ist ein JSON-Blob pro Item mit Struktur:
  ```json
  {
    "extra_fields": {
      "Feldname": {"type": "text", "value": "...", "position": 0, "group_id": 1}
    },
    "elabftw": {
      "extra_fields_groups": [{"id": 1, "name": "Properties"}, {"id": 2, "name": "Safety"}]
    }
  }
  ```
- Beim Update bestehender Items: **mergen, nicht überschreiben** — unbekannte/bereits
  vorhandene Felder müssen erhalten bleiben.
- Sinnvolle Gruppierung: Gruppe "Properties" (allgemeine Felder) vs. Gruppe "Safety"
  (P-Sätze, Schmelz-/Siedepunkt, Lagerklasse).

### Storage Units
- Hierarchisch (`parent_id`-Baum), z. B. Raum → Schrank → Fach.
- Auflösung/Erstellung folgt demselben Muster wie eLabFTWs eigene `createImmutable()`-Logik:
  Pfad-Segmente einzeln matchen/anlegen, damit doppelte Ordner vermieden werden.

### Container
- Tabelle `containers2items`, Felder u. a. `qty_stored` + `qty_unit`.
- `POST /api/v2/items/{item_id}/containers` — `storage_id` gehört in den **Body**, nicht in die URL.

### Berechtigungen (Schema 197 — Breaking Change ggü. älteren Versionen)
- `canread_base` / `canwrite_base` sind **eigene Integer-Spalten**, nicht Teil des
  `canread`-JSON-Objekts.
- Enum `BasePermissions`: Full=50, Org=40, Team=30, User=20, UserOnly=10.

### hide_main_text (Schema 196)
- Eigene Spalte auf Item-Ebene (ersetzt das alte `metadata.elabftw.display_main_text`).
- Für die Migration relevant: Nach dem Übertragen der Daten in Compound/Extra-Fields kann
  der alte HTML-Body per `PATCH {"hide_main_text": 1}` ausgeblendet werden, ohne ihn zu
  löschen (dient als Backup/Nachvollziehbarkeit).

---

## 4. CAS-Nummer — Validierung

CAS-Nummern haben eine Prüfsumme (identisch zur eLabFTW-internen Validierung in
`CompoundParams.php`):

```
Format: XXXXXXX-YY-Z  (2–7 Ziffern - 2 Ziffern - 1 Prüfziffer)
Prüfziffer = (Summe aller Ziffern von rechts nach links, gewichtet mit Position) mod 10
```

Wichtig für den Datenimport: ungültige/verstümmelte CAS-Nummern aus der Altdatenbank
kommen vor und sollten als Warnung markiert, aber nicht zum Abbruch führen.

---

## 5. Quellformat — CSV-Export der alten Chemikalien-Datenbank

Besonderheiten, die jeder Importweg (ob elAPI-basiert oder eigenständig) beachten muss:

- **Kein Header** — Spalten sind positionsbasiert.
- Trennzeichen: Semikolon; Encoding uneinheitlich (UTF-8/Latin-1/CP1252 — mit Fallback-Kette lesen).
- Am Dateiende stehen oft **PHP-Warnings** (`<br />`, `<b>Warning</b>: ...`) aus dem
  Export-Skript der Altdatenbank — müssen herausgefiltert werden.
- Raum-/Standortangabe steckt oft nur im **Kommentar-Header** der Datei
  (`# Inventarliste für Raum WIN-2.202`), nicht in einer eigenen Spalte.
- Menge und Einheit stehen **kombiniert** in einer Zelle (`"100 ml"`) → muss gesplittet
  und normalisiert werden (Einheiten-Schreibweisen wie `ml`/`ML` → `mL`).
- Dezimalwerte im **deutschen Format** (Komma statt Punkt), z. B. Molmasse `"236,34"`.
- P-Sätze enthalten Klammer-Annotationen mit Freitext, die entfernt werden müssen:
  `P501["einer anerkannten Abfallentsorgungsanlage"]` → `P501`.
- H-Sätze müssen auf die 16 GHS-Flags gemappt werden; Sonderfälle:
  - Klammer-Annotationen (`H370["",""]` → `H370`)
  - Suffix-Buchstaben (`H361f` → `H361`)
  - `H999` ist ein Platzhalter für "keine Einstufung" (alle Flags `false`)
- **Gleiche CAS-Nummer mehrfach** möglich (mehrere Flaschen/Chargen derselben Substanz)
  → Abgleich zwischen Quelle und eLabFTW braucht einen zusammengesetzten Schlüssel,
  z. B. CAS + Lieferanteninfo, sonst werden Datensätze fälschlich zusammengeführt.

---

## 6. Abgleichs-/Sync-Logik — Grundprinzip

Unabhängig von der konkreten Tool-Wahl (elAPI oder Eigenbau) braucht jeder Sync-Ansatz:

1. **Matching-Strategie** zwischen Quelle und Ziel (Priorität):
   1. CAS-Nummer + Lieferanteninfo (löst Duplikate auf)
   2. CAS-Nummer + Titel
   3. Titel allein (Fallback)
2. **Diff-Klassifizierung** pro Datensatz: `NEW` / `CHANGED` / `UNCHANGED` / `MISSING_IN_SOURCE`
   (Feld-für-Feld-Vergleich, damit man vor dem Schreiben sieht, was sich ändert)
3. **Dry-Run-Fähigkeit** — vor jedem Schreibzugriff eine Vorschau ohne API-Calls
4. **Selektiver Sync** — einzelne Datensätze aus- bzw. abwählbar, nicht nur Alles-oder-Nichts

---

# Anhang: Umsetzungsideen (bisher diskutiert)

Diese Punkte sind Ideen/Planungsstand aus den bisherigen Gesprächen — **kein
festgelegter Fahrplan**, sondern Diskussionsgrundlage für die Weiterarbeit:

### Bereits prototypisch umgesetzt (Python, "ChemSync")
- CSV-Reader mit den oben beschriebenen Parsern (Menge, Dezimalkomma, P-Satz-Bereinigung,
  CAS-Validierung, Raum-Extraktion aus Header)
- H-Satz → GHS-Flag-Mapper
- Metadata-JSON-Builder (inkl. Merge-Logik für bestehende Felder)
- Diff-Engine mit der oben beschriebenen Matching-Kaskade
- Sync-Engine (Create/Update, Dry-Run, CLI-Modus)
- Eigener API-Client (`api/client.py`) — **Kandidat für Ablösung durch elAPI**, siehe Abschnitt 1
- 26 Unit-Tests, alle grün
- Siehe `HANDOVER.md` im selben Verzeichnis für Datei-für-Datei-Stand und Setup-Anleitung

### Phase 2 (geplant, nicht begonnen)
- Grafische Oberfläche (PyQt6) mit 5 Schritten: Verbindung → CSV laden → Feld-Mapping →
  Diff-Ansicht (mit Farbcodierung Neu/Geändert/Unverändert/Fehlt) → Sync ausführen
  (mit Fortschrittsanzeige, Dry-Run-Option)

### Phase 3 (Ideen, unpriorisiert)
- Migration der **bestehenden** HTML-Body-Altdaten (nicht nur neuer CSV-Import) —
  Extraktion via Muster wie `<p>Feldname: Wert</p>>`, CAS-Regex-Suche im Fließtext
- Excel-Unterstützung als weitere Quelle neben CSV
- Direkte Anbindung an die alte Datenbank (statt CSV-Export als Zwischenschritt)
- Anreicherung fehlender Felder (SMILES, InChI, Molmasse) über die PubChem-API anhand CAS-Nummer
