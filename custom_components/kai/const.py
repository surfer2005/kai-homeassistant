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
CONF_POWER = "power_entities"           # Liste: Smartmeter-Sensoren → /api/landstrom/ingest

DEFAULT_SCAN_INTERVAL = 10             # Sekunden (Position/Geschwindigkeit)
DEFAULT_SMARTMETER_INTERVAL = 60       # Sekunden (Smartmeter, langsamer)
MIN_SCAN_INTERVAL = 1                   # bis 1 s (hohe Auflösung, z. B. für Unfall-Nachverfolgung)

TELEMETRY_PATH = "/api/telemetry/ingest"
SMARTMETER_PATH = "/api/landstrom/ingest"
