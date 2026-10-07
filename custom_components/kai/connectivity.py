"""Netz-Scanner an Bord: Geräte aus KAI ziehen, per IP (TCP/Ping) bzw. MAC (ARP) prüfen und
online/offline an KAIs Asset-Konnektivität melden. Ersetzt die separate HA-Automation."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket

import aiohttp

from .const import ASSET_CONN_PATH, SCAN_TARGETS_PATH

_LOGGER = logging.getLogger(__name__)


def _norm_mac(m: str) -> str:
    return re.sub(r"[^0-9a-f]", "", (m or "").lower())


def read_arp() -> dict[str, str]:
    """MAC(normalisiert) → IP aus der ARP-/Neighbor-Tabelle (Linux /proc/net/arp)."""
    out: dict[str, str] = {}
    try:
        with open("/proc/net/arp", encoding="ascii") as f:
            next(f, None)
            for line in f:
                p = line.split()
                if len(p) >= 4 and p[3] and p[3] != "00:00:00:00:00:00":
                    out[_norm_mac(p[3])] = p[0]
    except OSError:
        pass
    return out


async def _tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception:  # noqa: BLE001
        return False


async def _ping(host: str, timeout: int = 1) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(timeout), host,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        return await asyncio.wait_for(proc.wait(), timeout + 2) == 0
    except Exception:  # noqa: BLE001
        return False


async def _reachable(host: str, ports: list[int]) -> bool:
    if ports:
        results = await asyncio.gather(*(_tcp_open(host, p) for p in ports))
        if any(results):
            return True
    # Kein offener Port (oder keine Ports konfiguriert) → Ping als Rückfall.
    return await _ping(host)


async def _rdns(ip: str, timeout: float = 0.6) -> str | None:
    """Best-effort Reverse-DNS (Hostname) für ein entdecktes Gerät; leer, wenn es nicht auflöst."""
    try:
        loop = asyncio.get_running_loop()
        name, _, _ = await asyncio.wait_for(loop.run_in_executor(None, socket.gethostbyaddr, ip), timeout)
        return (name or "").split(".")[0] or None
    except Exception:  # noqa: BLE001
        return None


async def _arp_prime(host: str, ports: list[int]) -> None:
    """Ein Gerät einmal „anstupsen", damit der Kernel seine MAC auflöst (→ ARP-Tabelle).
    Per TCP-Verbindungsversuch statt Ping: funktioniert im HA-Container OHNE Root/Raw-Sockets.
    Ob der Port offen ist, ist egal — schon der Verbindungsversuch (auch „refused") löst ARP auf."""
    for p in (ports or [80, 443, 22]):
        try:
            fut = asyncio.open_connection(host, p)
            reader, writer = await asyncio.wait_for(fut, 0.5)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            return
        except (ConnectionRefusedError, OSError) as err:
            # „Connection refused" = Host ist da (ARP aufgelöst) → fertig.
            if isinstance(err, ConnectionRefusedError):
                return
            continue
        except asyncio.TimeoutError:
            continue
    # Rückfall: Ping (falls im Container doch verfügbar).
    await _ping(host)


async def _sweep(subnet: str, ports: list[int]) -> None:
    """Subnetz einmal anstupsen (TCP, Ping-Rückfall), damit die ARP-Tabelle gefüllt ist."""
    try:
        net = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        _LOGGER.warning("Ungültiges Scan-Subnetz: %s", subnet)
        return
    hosts = [str(h) for h in net.hosts()][:1024]
    sem = asyncio.Semaphore(64)

    async def one(ip):
        async with sem:
            await _arp_prime(ip, ports)

    await asyncio.gather(*(one(ip) for ip in hosts))


class KaiScanner:
    """Zieht Scan-Ziele aus KAI, prüft Erreichbarkeit, meldet Status zurück."""

    def __init__(self, session: aiohttp.ClientSession, base: str, key: str,
                 subnet: str | None, ports: list[int], discover: bool = True) -> None:
        self._session = session
        self._base = base.rstrip("/")
        self._key = key
        self._subnet = subnet
        self._ports = ports
        self._discover = discover

    async def _targets(self) -> list[dict]:
        async with self._session.get(
            f"{self._base}{SCAN_TARGETS_PATH}",
            headers={"X-API-Key": self._key},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            return (await resp.json(content_type=None)).get("items", [])

    async def _report(self, items: list[dict]) -> None:
        async with self._session.post(
            f"{self._base}{ASSET_CONN_PATH}",
            json=items,
            headers={"X-API-Key": self._key},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            await resp.read()

    async def run(self, _now=None) -> None:
        try:
            targets = await self._targets()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("KAI-Scan-Ziele konnten nicht geladen werden: %s", err)
            return
        # NICHT abbrechen, wenn KAI (noch) keine Ziele hat: die Entdeckung unbekannter Geräte soll
        # genau dann laufen (z. B. bevor Assets importiert sind). Nur abbrechen, wenn es nichts zu
        # tun gibt — keine Ziele UND keine Entdeckung.
        if not targets and not (self._discover and self._subnet):
            return
        need_arp = any(not t.get("ip") and t.get("macs") for t in targets)
        # Mit Subnetz wird gesweept, sobald MAC-Geräte zu prüfen sind ODER unbekannte Geräte
        # entdeckt werden sollen (DHCP-Geräte für die Zuordnung im Asset Manager sichtbar machen).
        do_arp = bool(self._subnet) and (need_arp or self._discover)
        if do_arp:
            await _sweep(self._subnet, self._ports)
        arp = read_arp() if do_arp else {}

        out: list[dict] = []
        known_macs: set[str] = set()
        for t in targets:
            name = t.get("name")
            if not name:
                continue
            online = False
            ip = t.get("ip")
            if ip:
                online = await _reachable(ip, self._ports)
            if not online:
                for m in t.get("macs") or []:
                    if _norm_mac(m) in arp:
                        online = True
                        break
            for m in t.get("macs") or []:
                n = _norm_mac(m)
                if n:
                    known_macs.add(n)
            out.append({"name": name, "entity": "network-scan", "domain": "network",
                        "status": "online" if online else "offline"})

        # Unbekannte Geräte im Netz (per ARP gefunden, zu keinem Ziel gehörend) als „nicht
        # zuordenbar" melden — mit MAC/IP/Hostname, damit sie im Asset Manager einem Asset
        # zugeordnet werden können. Danach matcht der nächste Scan sie automatisch über die MAC.
        if self._discover and arp:
            for mac_n, ip in arp.items():
                if mac_n in known_macs:
                    continue
                hostname = await _rdns(ip)
                out.append({"name": hostname or ip, "entity": mac_n, "domain": "network",
                            "status": "online", "mac": mac_n, "ip": ip, "hostname": hostname})

        entdeckt = sum(1 for o in out if o.get("entity") != "network-scan")
        _LOGGER.debug("KAI-Scan: %d Ziele aus KAI, %d ARP-Einträge, %d gemeldet (davon %d entdeckt)",
                      len(targets), len(arp), len(out), entdeckt)
        if out:
            try:
                await self._report(out)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("KAI-Konnektivität melden fehlgeschlagen: %s", err)
