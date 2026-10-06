<p align="center"><img src="icon.png" alt="KAI" width="96" height="96"></p>

# KAI Flottenbetrieb — Home-Assistant-Integration

Schickt Daten aus Home Assistant an **KAI**: je Schiff **Position, Geschwindigkeit, Kurs**
und optional **Smartmeter**-Werte. Gedacht für Flotten mit vielen Schiffen, deren Sensorik
in Home Assistant hängt.

## Was sie tut
- Liest konfigurierte HA-Entities (Tracker oder einzelne Sensoren) je Schiff.
- Sendet sie zyklisch an KAI:
  - Position/Geschwindigkeit/Kurs → `POST /api/telemetry/ingest`
  - Smartmeter → `POST /api/landstrom/ingest` (nur wenn ein Smartmeter-Key gesetzt ist)
- Zuordnung zum Schiff über die **Zulassungsnummer** (Schlüssel in KAI).
- Push-only, kein Cloud-Dienst, keine zusätzlichen Python-Abhängigkeiten.

## Installation über HACS
1. HACS → ⋮ → **Benutzerdefinierte Repositories** → dieses GitHub-Repo als Typ **Integration** hinzufügen.
2. „KAI Flottenbetrieb" installieren, Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → KAI**.

(Manuell: Ordner `custom_components/kai` nach `<config>/custom_components/` kopieren, neu starten.)

## Einrichten
1. In **KAI**: *Einstellungen → Schnittstellen → Schiffs-Telemetrie (Home Assistant)* →
   Ingest-Key „Neu erzeugen" + speichern. (Für Smartmeter zusätzlich den Landstrom-Ingest-Key.)
2. In **Home Assistant** beim Hinzufügen der Integration eintragen:
   - KAI-Adresse (z. B. `https://kai-bsb.de`)
   - Telemetrie Ingest-Key
   - optional Smartmeter Ingest-Key
   - Sende-Intervall (Standard 30 s)
3. Danach unter der Integration **„Konfigurieren" → Schiff hinzufügen**: Zulassungsnummer +
   Tracker **oder** einzelne Sensoren (Breite/Länge/Geschwindigkeit/Kurs) + optional Smartmeter-Sensoren.

## Hinweise
- `codeowners`/`documentation` in `custom_components/kai/manifest.json` und die URLs in dieser
  README auf das echte GitHub-Repo anpassen (Platzhalter `bsb`).
- Geschwindigkeit wird als **Knoten** erwartet; Kurs in **Grad** (0–360).
- Ein Tracker (device_tracker/person) liefert Koordinaten aus seinen Attributen
  `latitude`/`longitude` (und `speed`, falls vorhanden); einzelne Sensoren übersteuern den Tracker.

## Geplante Ausbaustufe
- **KAI-Connector**: Gegenrichtung (Daten aus KAI in Home Assistant als Sensoren/Geräte).
