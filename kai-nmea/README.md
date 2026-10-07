# KAI NMEA Bridge (Home-Assistant-Add-on)

Serviert **NMEA-0183 über TCP** aus den GPS-Werten eines Schiffs in Home Assistant —
für Seekarte/Plotter (z. B. Periskal INLAND ECDIS, „NMEA Winsock").

**Warum ein Add-on?** Es läuft als **eigener Dienst** (eigener Container) und übersteht
Neustarts von Home Assistant **Core**. Anders als die Integration bleibt der NMEA-Server
dadurch erreichbar — die Seekarte muss nach einem HA-Update/-Neustart **nicht** neu
„Speichern", die Verbindung bleibt bestehen (wie bei einem COM-Server).

## Installation
1. Einstellungen → Add-ons → Add-on-Store → oben rechts ⋮ → **Repositories**
   → `https://github.com/surfer2005/kai-homeassistant` hinzufügen.
2. Add-on **„KAI NMEA Bridge"** installieren.
3. Reiter **Konfiguration**: die GPS-Entities des Schiffs eintragen
   (`latitude_entity`, `longitude_entity`, optional `speed_entity`/`heading_entity`,
   optional `registration_number` nur zur Info im Log).
4. **Starten** + „Beim Booten starten" aktivieren (Standard).

## Seekarte einstellen
- NMEA über TCP (Winsock): **Host = IP des HA-Rechners**, **Port = 10110**.
- Der Host-Port lässt sich im Add-on unter **Netzwerk** ändern (Container-Port bleibt 10110).

## Hinweise
- Geschwindigkeit wird einheitenbewusst nach Knoten umgerechnet (km/h, m/s, mph, kn).
- Ein Add-on je Schiff/HA (ein TCP-Port). Mehr Schiffe auf einem HA → weitere Instanz/Port.
- Die normale KAI-Integration (Telemetrie/Smartmeter/Netz-Scan) bleibt davon unberührt;
  dieses Add-on ersetzt nur den NMEA-Ausgang durch eine neustart-feste Variante.
