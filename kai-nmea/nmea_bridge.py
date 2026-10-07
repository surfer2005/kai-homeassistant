#!/usr/bin/env python3
"""KAI NMEA Bridge (HA-Add-on): liest die GPS-Werte eines Schiffs aus Home Assistant
(über die Supervisor-API) und serviert daraus NMEA-0183 über TCP für Seekarte/Plotter.
Läuft als eigener Dienst → übersteht Neustarts von Home Assistant Core, die Seekarte
bleibt verbunden. Nur Python-Stdlib, keine Zusatzpakete."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from datetime import datetime

OPTIONS_PATH = "/data/options.json"
SUPERVISOR_API = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
PORT = 10110  # containerseitig fest; Host-Port in der Add-on-Netzwerk-Konfiguration änderbar

# Geschwindigkeit → Knoten (NMEA erwartet Knoten). Ohne Einheit gilt der Wert als Knoten.
_TO_KN = {
    "km/h": 0.5399568, "kmh": 0.5399568, "kph": 0.5399568,
    "mph": 0.8689762,
    "m/s": 1.9438445, "ms": 1.9438445,
    "kn": 1.0, "kt": 1.0, "kts": 1.0, "knot": 1.0, "knots": 1.0,
}


def _to_knots(val, unit):
    if val is None:
        return None
    if not unit:
        return val
    f = _TO_KN.get(str(unit).strip().lower())
    return round(val * f, 2) if f else val


# ---- NMEA-0183 (1:1 wie in der Integration) ----
def _cksum(body: str) -> str:
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"{c:02X}"


def _s(body: str) -> str:
    return f"${body}*{_cksum(body)}\r\n"


def _lat(v: float) -> str:
    h = "N" if v >= 0 else "S"
    v = abs(v); d = int(v)
    return f"{d:02d}{(v - d) * 60:07.4f},{h}"


def _lon(v: float) -> str:
    h = "E" if v >= 0 else "W"
    v = abs(v); d = int(v)
    return f"{d:03d}{(v - d) * 60:07.4f},{h}"


def build_sentences(lat, lon, sog_kn, cog, heading, when=None) -> list[str]:
    when = when or datetime.utcnow()
    t = when.strftime("%H%M%S.00"); dt = when.strftime("%d%m%y")
    sog = f"{sog_kn:.1f}" if sog_kn is not None else ""
    cogs = f"{cog:.1f}" if cog is not None else ""
    out: list[str] = []
    if lat is not None and lon is not None:
        out.append(_s(f"GPRMC,{t},A,{_lat(lat)},{_lon(lon)},{sog},{cogs},{dt},,"))
        out.append(_s(f"GPGGA,{t},{_lat(lat)},{_lon(lon)},1,08,0.9,0.0,M,,M,,"))
    sog_kmh = f"{sog_kn * 1.852:.1f}" if sog_kn is not None else ""
    out.append(_s(f"GPVTG,{cogs},T,,M,{sog},N,{sog_kmh},K,A"))
    if heading is not None:
        out.append(_s(f"GPHDT,{heading:.1f},T"))
    return out


def _load_options() -> dict:
    try:
        with open(OPTIONS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


def _get_state(entity: str):
    """(Wert, Einheit) einer HA-Entity über die Supervisor-API. Blockierend → im Executor nutzen."""
    if not entity:
        return (None, None)
    req = urllib.request.Request(
        f"{SUPERVISOR_API}/states/{entity}",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.load(r)
    except Exception as err:  # noqa: BLE001
        print(f"[kai-nmea] Zustand {entity} nicht lesbar: {err}", flush=True)
        return (None, None)
    st = d.get("state")
    if st in (None, "unknown", "unavailable", ""):
        return (None, (d.get("attributes") or {}).get("unit_of_measurement"))
    try:
        val = float(st)
    except (TypeError, ValueError):
        val = None
    return (val, (d.get("attributes") or {}).get("unit_of_measurement"))


class Bridge:
    def __init__(self, opts: dict) -> None:
        self.lat = opts.get("latitude_entity") or ""
        self.lon = opts.get("longitude_entity") or ""
        self.speed = opts.get("speed_entity") or ""
        self.heading = opts.get("heading_entity") or ""
        self.reg = opts.get("registration_number") or "?"
        self.clients: set[asyncio.StreamWriter] = set()

    async def _position(self):
        loop = asyncio.get_running_loop()
        lat, _ = await loop.run_in_executor(None, _get_state, self.lat)
        lon, _ = await loop.run_in_executor(None, _get_state, self.lon)
        if lat is None or lon is None:
            return None
        sog_kn = cog = None
        if self.speed:
            v, unit = await loop.run_in_executor(None, _get_state, self.speed)
            sog_kn = _to_knots(v, unit)
        if self.heading:
            cog, _ = await loop.run_in_executor(None, _get_state, self.heading)
        return (lat, lon, sog_kn, cog)

    async def _on_client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        self.clients.add(writer)
        print(f"[kai-nmea] Seekarte verbunden: {peer}", flush=True)
        try:
            while not reader.at_eof():
                if not await reader.read(256):
                    break
        except Exception:  # noqa: BLE001
            pass
        finally:
            self.clients.discard(writer)
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
            print(f"[kai-nmea] Seekarte getrennt: {peer}", flush=True)

    async def _tick(self):
        while True:
            await asyncio.sleep(1)
            if not self.clients:
                continue
            pos = await self._position()
            if not pos:
                continue
            data = "".join(build_sentences(pos[0], pos[1], pos[2], pos[3], pos[3])).encode("ascii", "ignore")
            for w in list(self.clients):
                try:
                    w.write(data)
                    await w.drain()
                except Exception:  # noqa: BLE001
                    self.clients.discard(w)
                    try:
                        w.close()
                    except Exception:  # noqa: BLE001
                        pass

    async def run(self):
        server = await asyncio.start_server(self._on_client, host="0.0.0.0", port=PORT)
        print(f"[kai-nmea] NMEA-TCP-Server für {self.reg} läuft auf 0.0.0.0:{PORT}", flush=True)
        await asyncio.gather(server.serve_forever(), self._tick())


def main():
    opts = _load_options()
    if not opts.get("latitude_entity") or not opts.get("longitude_entity"):
        print("[kai-nmea] Bitte latitude_entity und longitude_entity konfigurieren.", flush=True)
    asyncio.run(Bridge(opts).run())


if __name__ == "__main__":
    main()
