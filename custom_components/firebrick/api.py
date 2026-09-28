"""Minimal async client for the FireBrick web interface."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import re
from typing import Any
import xml.etree.ElementTree as ET

import aiohttp

NS = {"fb": "http://firebrick.ltd.uk/xml/statusv1"}

PATH_PORTS = "/status/ports/.xml"
PATH_PPPOE = "/status/pppoe/xml"
PATH_CQM_INDEX = "/cqm/json/"
PATH_SYSTEM_INFO = "/system/info"

_CQM_LINK_RE = re.compile(r"""href=["']\./([^"'/]+)\.json["']""")
_SERIAL_RE = re.compile(r"""class=["']serial["']>([^<]+)<""")
_UPTIME_RE = re.compile(r"^(?:(\d+):)?(\d+):(\d+):(\d+)$")

REQUEST_TIMEOUT = 15


class FirebrickError(Exception):
    """Base error talking to the FireBrick."""


class FirebrickConnectionError(FirebrickError):
    """The FireBrick could not be reached or returned something unexpected."""


class FirebrickAuthError(FirebrickError):
    """The FireBrick rejected the credentials."""


@dataclass(slots=True)
class Port:
    """A physical Ethernet port."""

    number: int
    portgroup: str | None
    link_up: bool
    speed: str | None
    duplex: str | None
    rx_bytes: int | None
    tx_bytes: int | None


@dataclass(slots=True)
class PppoeSession:
    """A PPPoE link."""

    name: str
    port: str | None
    state: str
    status: str | None
    uptime: timedelta | None
    local_ip: str | None
    local_ip6: str | None
    remote_ip: str | None
    graph: str | None

    @property
    def is_up(self) -> bool:
        """Return True if the session is established."""
        return self.state == "active" and self.status == "Active"


@dataclass(slots=True)
class CqmSample:
    """Most recent CQM sample containing latency information."""

    timestamp: datetime
    sent_polls: int
    lost_polls: int
    min_latency_ms: float | None
    ave_latency_ms: float | None
    max_latency_ms: float | None

    @property
    def packet_loss(self) -> float | None:
        """Return packet loss as a percentage."""
        if not self.sent_polls:
            return None
        return 100.0 * self.lost_polls / self.sent_polls


@dataclass(slots=True)
class CqmGraph:
    """A Constant Quality Monitoring graph."""

    name: str
    rx_bytes: int | None
    tx_bytes: int | None
    latest: CqmSample | None


@dataclass(slots=True)
class FirebrickStatus:
    """Everything fetched in a single poll."""

    firmware: str | None
    ports: dict[int, Port] = field(default_factory=dict)
    pppoe: dict[str, PppoeSession] = field(default_factory=dict)
    cqm: dict[str, CqmGraph] = field(default_factory=dict)


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _ns_to_ms(value: Any) -> float | None:
    return value / 1_000_000 if isinstance(value, (int, float)) else None


def parse_uptime(value: str | None) -> timedelta | None:
    """Parse FireBrick uptime strings such as '5:21:55:43' (d:hh:mm:ss)."""
    if not value or not (match := _UPTIME_RE.match(value)):
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def _parse_xml(text: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except ET.ParseError as err:
        raise FirebrickConnectionError(f"Invalid XML from FireBrick: {err}") from err


def parse_ports(text: str) -> tuple[str | None, dict[int, Port]]:
    """Parse /status/ports/.xml into ports keyed by number."""
    root = _parse_xml(text)
    counters: dict[str, dict[str, int | None]] = {}
    for stat in root.iterfind("fb:eth-stats/fb:eth-stat", NS):
        counters.setdefault(stat.get("port", ""), {})[stat.get("stat", "")] = _int(
            stat.get("total")
        )

    ports: dict[int, Port] = {}
    for outer in root.iterfind("fb:port", NS):
        if (inner := outer.find("fb:port", NS)) is None:
            continue
        if (number := _int(inner.get("number"))) is None:
            continue
        stats = counters.get(f"Port {number}", {})
        portgroup = inner.get("portgroup")
        ports[number] = Port(
            number=number,
            portgroup=None if portgroup == "not assigned" else portgroup,
            link_up=inner.get("link") == "Up",
            speed=inner.get("speed"),
            duplex=inner.get("duplex"),
            rx_bytes=stats.get("Rx good bytes"),
            tx_bytes=stats.get("Tx bytes"),
        )
    return root.get("firmware-version"), ports


def parse_pppoe(text: str) -> dict[str, PppoeSession]:
    """Parse /status/pppoe/xml into sessions keyed by name."""
    root = _parse_xml(text)
    sessions: dict[str, PppoeSession] = {}
    for elem in root.iterfind("fb:pppoe/*", NS):
        name = elem.get("name") or elem.get("port")
        if not name:
            continue
        sessions[name] = PppoeSession(
            name=name,
            port=elem.get("port"),
            state=elem.tag.rpartition("}")[2],
            status=elem.get("status"),
            uptime=parse_uptime(elem.get("uptime")),
            local_ip=elem.get("local-ip"),
            local_ip6=elem.get("local-ip6"),
            remote_ip=elem.get("remote-ip"),
            graph=elem.get("graph"),
        )
    return sessions


def parse_cqm_index(text: str) -> list[str]:
    """Return graph names listed on /cqm/json/."""
    return list(dict.fromkeys(_CQM_LINK_RE.findall(text)))


def parse_cqm(name: str, text: str) -> CqmGraph:
    """Parse a /cqm/<name>.json document."""
    try:
        data = json.loads(text)
    except ValueError as err:
        raise FirebrickConnectionError(f"Invalid CQM JSON for {name}: {err}") from err

    latest: CqmSample | None = None
    for row in reversed(data.get("data") or []):
        if not row.get("sent-polls"):
            continue
        latest = CqmSample(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            sent_polls=row["sent-polls"],
            lost_polls=row.get("lost-polls", 0),
            min_latency_ms=_ns_to_ms(row.get("min-latency-ns")),
            ave_latency_ms=_ns_to_ms(row.get("ave-latency-ns")),
            max_latency_ms=_ns_to_ms(row.get("max-latency-ns")),
        )
        break

    return CqmGraph(
        name=name,
        rx_bytes=data.get("rx-bytes-to-date"),
        tx_bytes=data.get("tx-bytes-to-date"),
        latest=latest,
    )


class FirebrickClient:
    """Talks to a FireBrick over HTTP(S) using Basic auth."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        username: str,
        password: str,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._url = url.rstrip("/")
        self._headers = {"Authorization": aiohttp.encode_basic_auth(username, password)}

    async def _get(self, path: str) -> str:
        try:
            async with self._session.get(
                f"{self._url}{path}",
                headers=self._headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                # Bad credentials get a 303 redirect to /login/.
                if resp.status in (401, 403) or 300 <= resp.status < 400:
                    raise FirebrickAuthError(f"Access denied for {path}")
                if resp.status != 200:
                    raise FirebrickConnectionError(f"HTTP {resp.status} for {path}")
                return await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FirebrickConnectionError(f"Error fetching {path}: {err}") from err

    async def async_get_serial(self) -> str:
        """Return the unit serial number."""
        if match := _SERIAL_RE.search(await self._get(PATH_SYSTEM_INFO)):
            return match.group(1).strip()
        raise FirebrickConnectionError("Serial number not found on unit info page")

    async def async_get_status(self) -> FirebrickStatus:
        """Fetch ports, PPPoE and all CQM graphs."""
        ports_text, pppoe_text, cqm_index = await asyncio.gather(
            self._get(PATH_PORTS), self._get(PATH_PPPOE), self._get(PATH_CQM_INDEX)
        )
        firmware, ports = parse_ports(ports_text)
        names = parse_cqm_index(cqm_index)
        cqm_texts = await asyncio.gather(
            *(self._get(f"/cqm/{name}.json") for name in names)
        )
        return FirebrickStatus(
            firmware=firmware,
            ports=ports,
            pppoe=parse_pppoe(pppoe_text),
            cqm={
                name: parse_cqm(name, text)
                for name, text in zip(names, cqm_texts, strict=True)
            },
        )
