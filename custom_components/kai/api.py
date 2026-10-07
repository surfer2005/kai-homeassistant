"""Schlanker KAI-Client: Telemetrie + Smartmeter per REST (X-API-Key)."""
from __future__ import annotations

import logging

import aiohttp

from .const import SMARTMETER_PATH, TELEMETRY_PATH

_LOGGER = logging.getLogger(__name__)


class KaiApiError(Exception):
    """Fehler bei der Kommunikation mit KAI."""


class KaiClient:
    """Postet Telemetrie-/Smartmeter-Daten an eine KAI-Instanz."""

    def __init__(self, session: aiohttp.ClientSession, url: str, api_key: str,
                 smartmeter_key: str | None = None) -> None:
        self._session = session
        self._base = url.rstrip("/")
        self._api_key = api_key
        # Ein Schlüssel für alles: fehlt ein eigener Smartmeter-Schlüssel, gilt der Hauptschlüssel.
        self._smartmeter_key = smartmeter_key or api_key

    async def _post(self, path: str, key: str, payload) -> dict:
        try:
            async with self._session.post(
                f"{self._base}{path}",
                json=payload,
                headers={"X-API-Key": key},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
                if resp.status == 401:
                    raise KaiApiError("Ungültiger API-Key (401)")
                if resp.status >= 400:
                    raise KaiApiError(f"HTTP {resp.status}: {text[:200]}")
                try:
                    return await resp.json(content_type=None)
                except Exception:  # noqa: BLE001
                    return {}
        except aiohttp.ClientError as err:
            raise KaiApiError(f"Verbindungsfehler: {err}") from err

    async def validate(self) -> None:
        """Verbindung + Telemetrie-Key prüfen (leeres Array → 200 bei gültigem Key)."""
        await self._post(TELEMETRY_PATH, self._api_key, [])

    async def send_positions(self, positions: list[dict]) -> dict:
        if not positions:
            return {"inserted": 0}
        return await self._post(TELEMETRY_PATH, self._api_key, positions)

    async def send_smartmeter(self, readings: list[dict]) -> dict:
        if not readings or not self._smartmeter_key:
            return {"inserted": 0}
        return await self._post(SMARTMETER_PATH, self._smartmeter_key, readings)
