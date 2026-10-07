"""Config- und Options-Flow der KAI-Integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KaiApiError, KaiClient
from .const import (
    CONF_API_KEY,
    CONF_HEADING,
    CONF_LAT,
    CONF_CONN_INTERVAL,
    CONF_HA_KEY,
    CONF_LON,
    CONF_NMEA_PORT,
    CONF_SCAN_PORTS,
    CONF_SCAN_SUBNET,
    CONF_POWER,
    CONF_POWER_AREAS,
    CONF_POWER_LABELS,
    CONF_REGISTRATION,
    CONF_SCAN_INTERVAL,
    CONF_SHIPS,
    CONF_SMARTMETER_INTERVAL,
    CONF_SMARTMETER_KEY,
    CONF_SPEED,
    CONF_TRACKER,
    CONF_URL,
    DEFAULT_CONN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_PORTS,
    DEFAULT_SMARTMETER_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

CONNECTION_SCHEMA = vol.Schema({
    vol.Required(CONF_URL): selector.TextSelector(),
    vol.Required(CONF_API_KEY): selector.TextSelector(),
    vol.Optional(CONF_SMARTMETER_KEY, default=""): selector.TextSelector(),
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): selector.NumberSelector(
        selector.NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=3600, unit_of_measurement="s",
                                      mode=selector.NumberSelectorMode.BOX)
    ),
    vol.Optional(CONF_SMARTMETER_INTERVAL, default=DEFAULT_SMARTMETER_INTERVAL): selector.NumberSelector(
        selector.NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=86400, unit_of_measurement="s",
                                      mode=selector.NumberSelectorMode.BOX)
    ),
    vol.Optional(CONF_HA_KEY, default=""): selector.TextSelector(),
    vol.Optional(CONF_SCAN_SUBNET, default=""): selector.TextSelector(),
    vol.Optional(CONF_SCAN_PORTS, default=DEFAULT_SCAN_PORTS): selector.TextSelector(),
})


def _ship_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}

    def marker(key, required=False):
        # Vorgabe NUR setzen, wenn ein Wert existiert — sonst meldet ein leeres
        # EntitySelector-Feld "Entity None is neither a valid entity ID".
        if required:
            return vol.Required(key, default=d.get(key, ""))
        val = d.get(key)
        return vol.Optional(key, default=val) if val not in (None, "", []) else vol.Optional(key)

    entity = lambda *domains, multiple=False: selector.EntitySelector(  # noqa: E731
        selector.EntitySelectorConfig(domain=list(domains), multiple=multiple))

    return vol.Schema({
        marker(CONF_REGISTRATION, required=True): selector.TextSelector(),
        marker(CONF_TRACKER): entity("device_tracker", "person"),
        marker(CONF_LAT): entity("sensor", "input_number"),
        marker(CONF_LON): entity("sensor", "input_number"),
        marker(CONF_SPEED): entity("sensor", "input_number"),
        marker(CONF_HEADING): entity("sensor", "input_number"),
        # Smartmeter skaliert über Labels/Bereiche (ALLE passenden Sensoren) statt Einzelauswahl.
        marker(CONF_POWER_LABELS): selector.LabelSelector(selector.LabelSelectorConfig(multiple=True)),
        marker(CONF_POWER_AREAS): selector.AreaSelector(selector.AreaSelectorConfig(multiple=True)),
        marker(CONF_POWER): entity("sensor", multiple=True),
        # NMEA-0183-TCP-Ausgang für Seekarte/Plotter (leer = aus; Standard-Port 10110).
        marker(CONF_NMEA_PORT): selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=65535, mode=selector.NumberSelectorMode.BOX)),
    })


async def _validate(hass, data: dict) -> str | None:
    """Verbindung prüfen. Gibt eine Fehlerkennung zurück oder None bei Erfolg."""
    client = KaiClient(async_get_clientsession(hass), data[CONF_URL], data[CONF_API_KEY])
    try:
        await client.validate()
    except KaiApiError as err:
        return "invalid_auth" if "401" in str(err) else "cannot_connect"
    return None


class KaiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Verbindung zu einer KAI-Instanz einrichten."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            await self.async_set_unique_id(url)
            self._abort_if_unique_id_configured()
            err = await _validate(self.hass, {CONF_URL: url, CONF_API_KEY: user_input[CONF_API_KEY]})
            if err:
                errors["base"] = err
            else:
                return self.async_create_entry(
                    title=f"KAI ({url})",
                    data={
                        CONF_URL: url,
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_SMARTMETER_KEY: user_input.get(CONF_SMARTMETER_KEY, "") or "",
                        CONF_HA_KEY: user_input.get(CONF_HA_KEY, "") or "",
                        CONF_SCAN_SUBNET: user_input.get(CONF_SCAN_SUBNET, "") or "",
                        CONF_SCAN_PORTS: user_input.get(CONF_SCAN_PORTS, DEFAULT_SCAN_PORTS) or DEFAULT_SCAN_PORTS,
                    },
                    options={
                        CONF_SCAN_INTERVAL: int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                        CONF_SMARTMETER_INTERVAL: int(user_input.get(CONF_SMARTMETER_INTERVAL, DEFAULT_SMARTMETER_INTERVAL)),
                        CONF_CONN_INTERVAL: DEFAULT_CONN_INTERVAL,
                        CONF_SHIPS: [],
                    },
                )
        return self.async_show_form(step_id="user", data_schema=CONNECTION_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return KaiOptionsFlow(config_entry)


class KaiOptionsFlow(OptionsFlow):
    """Schiffe/Entities verwalten + Sende-Intervall."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    def _ships(self) -> list[dict]:
        return list(self.entry.options.get(CONF_SHIPS, []))

    def _save(self, ships: list[dict] | None = None, interval: int | None = None, sm_interval: int | None = None, conn_interval: int | None = None):
        opts = dict(self.entry.options)
        if ships is not None:
            opts[CONF_SHIPS] = ships
        if interval is not None:
            opts[CONF_SCAN_INTERVAL] = interval
        if sm_interval is not None:
            opts[CONF_SMARTMETER_INTERVAL] = sm_interval
        if conn_interval is not None:
            opts[CONF_CONN_INTERVAL] = conn_interval
        return self.async_create_entry(title="", data=opts)

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_ship", "remove_ship", "interval"],
        )

    async def async_step_add_ship(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            ship = {k: v for k, v in user_input.items() if v not in (None, "", [])}
            ships = self._ships()
            ships.append(ship)
            return self._save(ships=ships)
        return self.async_show_form(step_id="add_ship", data_schema=_ship_schema())

    async def async_step_remove_ship(self, user_input=None) -> ConfigFlowResult:
        ships = self._ships()
        if not ships:
            return self._save(ships=ships)
        if user_input is not None:
            keep = [s for s in ships if s.get(CONF_REGISTRATION) not in user_input.get("remove", [])]
            return self._save(ships=keep)
        regs = [s.get(CONF_REGISTRATION, "?") for s in ships]
        schema = vol.Schema({
            vol.Optional("remove", default=[]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=regs, multiple=True,
                                              mode=selector.SelectSelectorMode.LIST)),
        })
        return self.async_show_form(step_id="remove_ship", data_schema=schema)

    async def async_step_interval(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(interval=int(user_input[CONF_SCAN_INTERVAL]),
                              sm_interval=int(user_input[CONF_SMARTMETER_INTERVAL]),
                              conn_interval=int(user_input.get(CONF_CONN_INTERVAL, DEFAULT_CONN_INTERVAL)))
        schema = vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL,
                         default=int(self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))):
                selector.NumberSelector(selector.NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL, max=3600, unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX)),
            vol.Required(CONF_SMARTMETER_INTERVAL,
                         default=int(self.entry.options.get(CONF_SMARTMETER_INTERVAL, DEFAULT_SMARTMETER_INTERVAL))):
                selector.NumberSelector(selector.NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL, max=86400, unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX)),
            vol.Required(CONF_CONN_INTERVAL,
                         default=int(self.entry.options.get(CONF_CONN_INTERVAL, DEFAULT_CONN_INTERVAL))):
                selector.NumberSelector(selector.NumberSelectorConfig(
                    min=10, max=86400, unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX)),
        })
        return self.async_show_form(step_id="interval", data_schema=schema)
