"""NMEA-0183-Sätze aus Position/Geschwindigkeit/Kurs bauen (für den TCP-Ausgang an Seekarten)."""
from __future__ import annotations

from datetime import datetime


def _cksum(body: str) -> str:
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"{c:02X}"


def _s(body: str) -> str:
    return f"${body}*{_cksum(body)}\r\n"


def _lat(v: float) -> str:
    h = "N" if v >= 0 else "S"
    v = abs(v)
    d = int(v)
    return f"{d:02d}{(v - d) * 60:07.4f},{h}"


def _lon(v: float) -> str:
    h = "E" if v >= 0 else "W"
    v = abs(v)
    d = int(v)
    return f"{d:03d}{(v - d) * 60:07.4f},{h}"


def build_sentences(lat, lon, sog_kn, cog, heading, when: datetime | None = None) -> list[str]:
    """RMC + GGA + VTG (+ HDT wenn Steuerkurs vorhanden). sog_kn in Knoten, cog/heading in Grad."""
    when = when or datetime.utcnow()
    t = when.strftime("%H%M%S.00")
    dt = when.strftime("%d%m%y")
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
