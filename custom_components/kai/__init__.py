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
    CONF_SMARTMETER_KEY,
    CONF_SPEED,
    CONF_TRACKER,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
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
        lat = lon = speed = heading = None
        tracker = ship.get(CONF_TRACKER)
        if tracker:
            st = self.hass.states.get(tracker)
            if st and st.state not in _UNUSABLE:
                lat = _num(st.attributes.get("latitude"))
                lon = _num(st.attributes.get("longitude"))
                speed = _num(st.attributes.get("speed"))
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
                # Einheit des Sensors beachten (z. B. Teltonika liefert km/h) → nach Knoten.
                speed = _to_knots(val, st.attributes.get("unit_of_measurement"))
            elif setter == "heading":
                heading = val
        if lat is None and lon is None and speed is None and heading is None:
            return None
        return {
            "registration_number": reg,
            "latitude": lat,
            "longitude": lon,
            "speed_kn": speed,
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

    async def async_update(self, _now=None) -> None:
        positions = self._collect_positions()
        readings = self._readings()
        if not positions and not readings:
            return
        try:
            if positions:
                await self.client.send_positions(positions)
            if readings:
                await self.client.send_smartmeter(readings)
        except KaiApiError as err:
            _LOGGER.warning("KAI-Übertragung fehlgeschlagen: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = KaiClient(
        session,
        entry.data[CONF_URL],
        entry.data[CONF_API_KEY],
        entry.data.get(CONF_SMARTMETER_KEY) or None,
    )
    sender = KaiSender(hass, client, entry)
    interval = max(10, int(entry.options.get(CONF_SCAN_INTERVAL,
                   entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))))
    unsub = async_track_time_interval(hass, sender.async_update, timedelta(seconds=interval))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"sender": sender, "unsub": unsub}
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    # Sofort einmal senden, nicht erst nach dem ersten Intervall.
    hass.async_create_task(sender.async_update())
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and data.get("unsub"):
        data["unsub"]()
    return True
