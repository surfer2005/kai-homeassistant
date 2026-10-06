"""KAI Flottenbetrieb — schickt HA-Daten (Position/Geschwindigkeit/Smartmeter) an KAI."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import KaiApiError, KaiClient
from .const import (
    CONF_API_KEY,
    CONF_HEADING,
    CONF_LAT,
    CONF_LON,
    CONF_POWER,
    CONF_REGISTRATION,
    CONF_SCAN_INTERVAL,
    CONF_SHIPS,
    CONF_SMARTMETER_INTERVAL,
    CONF_SMARTMETER_KEY,
    CONF_SPEED,
    CONF_TRACKER,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SMARTMETER_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
_UNUSABLE = (None, "", STATE_UNKNOWN, STATE_UNAVAILABLE)


def _num(value):
    try:
        if value in _UNUSABLE:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# Geschwindigkeit nach Knoten umrechnen — KAI speichert speed_kn. Einheit kommt aus dem Sensor
# (unit_of_measurement); unbekannt/leer → unverändert übernehmen.
_TO_KN = {
    "km/h": 1 / 1.852, "kmh": 1 / 1.852, "kph": 1 / 1.852,
    "mph": 1 / 1.150779,
    "m/s": 1.943844, "ms": 1.943844,
    "kn": 1.0, "kt": 1.0, "kts": 1.0, "knot": 1.0, "knots": 1.0,
}


def _to_knots(val, unit):
    if val is None:
        return None
    if not unit:
        return val
    factor = _TO_KN.get(str(unit).strip().lower())
    return round(val * factor, 2) if factor else val


# km/h parallel — KAI speichert beides (speed_kn + speed_kmh).
_TO_KMH = {
    "km/h": 1.0, "kmh": 1.0, "kph": 1.0,
    "mph": 1.609344,
    "m/s": 3.6, "ms": 3.6,
    "kn": 1.852, "kt": 1.852, "kts": 1.852, "knot": 1.852, "knots": 1.852,
}


def _to_kmh(val, unit):
    if val is None:
        return None
    if not unit:
        return round(val * 1.852, 2)  # ohne Einheit: Attribut-Speed gilt als Knoten
    factor = _TO_KMH.get(str(unit).strip().lower())
    return round(val * factor, 2) if factor else val


class KaiSender:
    """Liest konfigurierte HA-Entities und postet sie zyklisch an KAI."""

    def __init__(self, hass: HomeAssistant, client: KaiClient, entry: ConfigEntry) -> None:
        self.hass = hass
        self.client = client
        self.entry = entry

    def _ships(self) -> list[dict]:
        return self.entry.options.get(CONF_SHIPS, [])

    def _position_for(self, ship: dict) -> dict | None:
        reg = (ship.get(CONF_REGISTRATION) or "").strip()
        if not reg:
            return None
        lat = lon = speed = speed_kmh = heading = None
        tracker = ship.get(CONF_TRACKER)
        if tracker:
            st = self.hass.states.get(tracker)
            if st and st.state not in _UNUSABLE:
                lat = _num(st.attributes.get("latitude"))
                lon = _num(st.attributes.get("longitude"))
                sp = _num(st.attributes.get("speed"))
                if sp is not None:
                    unit = st.attributes.get("speed_unit") or st.attributes.get("unit_of_measurement")
                    speed = _to_knots(sp, unit)
                    speed_kmh = _to_kmh(sp, unit)
        # Einzelne Sensoren übersteuern den Tracker, wenn gesetzt.
        for key, setter in (
            (CONF_LAT, "lat"), (CONF_LON, "lon"), (CONF_SPEED, "speed"), (CONF_HEADING, "heading"),
        ):
            ent = ship.get(key)
            if not ent:
                continue
            st = self.hass.states.get(ent)
            val = _num(st.state) if st else None
            if val is None:
                continue
            if setter == "lat":
                lat = val
            elif setter == "lon":
                lon = val
            elif setter == "speed":
                # Einheit des Sensors beachten (z. B. Teltonika liefert km/h) → beide Einheiten.
                unit = st.attributes.get("unit_of_measurement")
                speed = _to_knots(val, unit)
                speed_kmh = _to_kmh(val, unit)
            elif setter == "heading":
                heading = val
        if lat is None and lon is None and speed is None and speed_kmh is None and heading is None:
            return None
        return {
            "registration_number": reg,
            "latitude": lat,
            "longitude": lon,
            "speed_kn": speed,
            "speed_kmh": speed_kmh,
            "heading_deg": heading,
            "source": "homeassistant",
            "recorded_at": dt_util.utcnow().isoformat(),
        }

    def _readings(self) -> list[dict]:
        out: list[dict] = []
        for ship in self._ships():
            for ent in ship.get(CONF_POWER, []) or []:
                st = self.hass.states.get(ent)
                val = _num(st.state) if st else None
                if val is None:
                    continue
                out.append({
                    "entity_id": ent,
                    "name": (st.attributes.get("friendly_name") if st else None) or ent,
                    "unit": st.attributes.get("unit_of_measurement") if st else None,
                    "value": val,
                })
        return out

    @callback
    def _collect_positions(self) -> list[dict]:
        out = []
        for ship in self._ships():
            pos = self._position_for(ship)
            if pos:
                out.append(pos)
        return out

    async def async_update_positions(self, _now=None) -> None:
        positions = self._collect_positions()
        if not positions:
            return
        try:
            await self.client.send_positions(positions)
        except KaiApiError as err:
            _LOGGER.warning("KAI-Positionsübertragung fehlgeschlagen: %s", err)

    async def async_update_smartmeter(self, _now=None) -> None:
        readings = self._readings()
        if not readings:
            return
        try:
            await self.client.send_smartmeter(readings)
        except KaiApiError as err:
            _LOGGER.warning("KAI-Smartmeterübertragung fehlgeschlagen: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = KaiClient(
        session,
        entry.data[CONF_URL],
        entry.data[CONF_API_KEY],
        entry.data.get(CONF_SMARTMETER_KEY) or None,
    )
    sender = KaiSender(hass, client, entry)
    pos_interval = max(1, int(entry.options.get(CONF_SCAN_INTERVAL,
                       entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))))
    sm_interval = max(1, int(entry.options.get(CONF_SMARTMETER_INTERVAL, DEFAULT_SMARTMETER_INTERVAL)))
    unsubs = [
        async_track_time_interval(hass, sender.async_update_positions, timedelta(seconds=pos_interval)),
        async_track_time_interval(hass, sender.async_update_smartmeter, timedelta(seconds=sm_interval)),
    ]

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"sender": sender, "unsubs": unsubs}
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    # Sofort einmal senden, nicht erst nach dem ersten Intervall.
    hass.async_create_task(sender.async_update_positions())
    hass.async_create_task(sender.async_update_smartmeter())
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        for unsub in data.get("unsubs", []):
            unsub()
    return True
