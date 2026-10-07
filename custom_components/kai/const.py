"""Konstanten der KAI-Integration."""

DOMAIN = "kai"

# Config-Entry-Daten
CONF_URL = "url"
CONF_API_KEY = "api_key"               # telemetry_ingest_key (Position/Geschwindigkeit/Kurs)
CONF_SMARTMETER_KEY = "smartmeter_key"  # landstrom_ingest_key (optional, Smartmeter)
CONF_SCAN_INTERVAL = "scan_interval"               # Position/Geschwindigkeit
CONF_SMARTMETER_INTERVAL = "smartmeter_scan_interval"

# Options
CONF_SHIPS = "ships"

# Je Schiff
CONF_REGISTRATION = "registration_number"
CONF_TRACKER = "tracker_entity"         # device_tracker/person mit lat/lon (+ ggf. speed) in Attributen
CONF_LAT = "latitude_entity"            # alternativ: eigener Sensor
CONF_LON = "longitude_entity"
CONF_SPEED = "speed_entity"
CONF_HEADING = "heading_entity"
CONF_POWER = "power_entities"           # Liste: einzelne Smartmeter-Sensoren → /api/landstrom/ingest
CONF_POWER_LABELS = "power_labels"      # HA-Labels: ALLE Sensoren mit diesem Label
CONF_POWER_AREAS = "power_areas"        # HA-Bereiche: ALLE Sensoren in diesem Bereich
CONF_NMEA_PORT = "nmea_port"            # TCP-Port für NMEA-0183-Ausgabe (Seekarte/Plotter)

DEFAULT_NMEA_PORT = 10110               # IANA-Standardport für NMEA 0183 über TCP

DEFAULT_SCAN_INTERVAL = 10             # Sekunden (Position/Geschwindigkeit)
DEFAULT_SMARTMETER_INTERVAL = 60       # Sekunden (Smartmeter, langsamer)
MIN_SCAN_INTERVAL = 1                   # bis 1 s (hohe Auflösung, z. B. für Unfall-Nachverfolgung)

TELEMETRY_PATH = "/api/telemetry/ingest"
SMARTMETER_PATH = "/api/landstrom/ingest"
SCAN_TARGETS_PATH = "/api/asset-manager/scan-targets"
ASSET_CONN_PATH = "/api/asset-manager/ha-connectivity"

# Netz-Scan (Asset-Konnektivität an Bord): Geräte aus KAI ziehen, per IP/MAC prüfen, Status melden.
CONF_HA_KEY = "ha_key"                   # am_ha_ingest_key (Scan-Ziele lesen + Status melden)
CONF_SCAN_SUBNET = "scan_subnet"         # z. B. 192.168.1.0/24 (für MAC/DHCP-Geräte: ARP-Sweep)
CONF_SCAN_PORTS = "scan_ports"           # TCP-Ports für den Erreichbarkeits-Check
CONF_CONN_INTERVAL = "conn_scan_interval"
CONF_SCAN_DISCOVER = "scan_discover"   # unbekannte Netz-Geraete als „nicht zuordenbar" melden
DEFAULT_CONN_INTERVAL = 60
DEFAULT_SCAN_PORTS = "80,443,22"
DEFAULT_SCAN_DISCOVER = True
