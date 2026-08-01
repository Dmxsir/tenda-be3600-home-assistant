"""Small async client for the local Tenda BE3600 web API."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

_IV = b"EU5H62G9ICGRNI43"
_MODULES = (
    "meshTopo",
    "wanStatus",
    "deviceListNotNeedRate",
    "systemCfg",
    "apModeStatus",
    "workMode",
    "deviceVersionList",
)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_]+$")
_TOKEN = re.compile(r"^[0-9a-fA-F]{32}$")
_LOGGER = logging.getLogger(__name__)


class TendaError(Exception):
    """Base API error."""


class TendaAuthError(TendaError):
    """Authentication failed."""


class TendaLockedError(TendaError):
    """The router has temporarily locked administrator login."""


class TendaConnectionError(TendaError):
    """The router could not be reached."""


class TendaProtocolError(TendaError):
    """The router returned an unexpected response."""


class _SessionExpired(Exception):
    pass


def hash_password(password: str) -> str:
    """Return the uppercase MD5 form expected by the router."""
    return hashlib.md5(password.encode(), usedforsecurity=False).hexdigest().upper()


class TendaApi:
    """Client using an injected aiohttp-compatible session."""

    def __init__(self, session: Any, host: str, password_digest: str) -> None:
        candidate = host.strip()
        parts = urlsplit(candidate if "://" in candidate else f"http://{candidate}")
        if (
            parts.scheme not in {"http", "https"}
            or not parts.netloc
            or parts.username is not None
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Invalid router host")
        if not re.fullmatch(r"[0-9A-Fa-f]{32}", password_digest):
            raise ValueError("Invalid password digest")

        self._session = session
        self._base_url = f"{parts.scheme}://{parts.netloc}"
        self._password_digest = password_digest.upper()
        self._stok: str | None = None
        self._sign: str | None = None
        self._cookie: str | None = None

    async def async_close(self) -> None:
        """Close the owned HTTP session."""
        await self._session.close()

    async def async_login(self) -> None:
        """Authenticate without consuming an attempt while already locked."""
        self._cookie = None
        info = _json_object(
            await self._request(
                "GET", "/goform/loginInfo", params={"rand": time.time_ns()}
            )
        )
        info = info.get("loginInfo", info)
        if not isinstance(info, dict):
            raise TendaProtocolError("Invalid login status response")
        left = _integer(info.get("leftTimes"))
        if _truthy(info.get("isLocked")) or (
            _truthy(info.get("isLimit")) and left is not None and left <= 0
        ):
            raise TendaLockedError("Router login is temporarily locked")

        response = _json_object(
            await self._request(
                "POST",
                "/login/Auth",
                json={"userName": "admin", "password": self._password_digest},
                capture_cookie=True,
            )
        )
        if _integer(response.get("errCode")) != 0:
            raise TendaAuthError("Invalid router credentials")

        sign, stok = response.get("sign"), response.get("stok")
        if (
            not isinstance(sign, str)
            or len(sign.encode()) != 16
            or not isinstance(stok, str)
            or not _TOKEN.fullmatch(stok)
        ):
            raise TendaProtocolError("Invalid login response")
        self._sign, self._stok = sign, stok

    async def async_get_snapshot(self) -> dict[str, Any]:
        """Fetch and normalize one complete read-only snapshot."""
        if self._stok is None:
            await self.async_login()

        for attempt in range(2):
            try:
                return parse_snapshot(await self._async_get_modules(_MODULES))
            except _SessionExpired:
                self._stok = self._sign = self._cookie = None
                if attempt:
                    raise TendaProtocolError("Router rejected authenticated session") from None
                await self.async_login()
        raise AssertionError("unreachable")

    async def _async_get_modules(self, modules: tuple[str, ...]) -> dict[str, Any]:
        if not self._stok or not self._sign:
            raise _SessionExpired
        if not all(_SAFE_NAME.fullmatch(module) for module in modules):
            raise ValueError("Invalid module name")

        text = await self._request(
            "GET",
            f"/;stok={self._stok}/goform/getModules",
            params={
                "rand": time.time_ns(),
                "modules": ",".join(modules),
                "timerRefresh": 1,
            },
        )
        if _is_html(text):
            raise _SessionExpired
        wrapped = _json_object(text)
        data = wrapped.get("data")
        if not isinstance(data, str):
            raise TendaProtocolError("Missing encrypted response data")
        return _decrypt_data(data, self._sign)

    async def _request(self, method: str, path: str, **kwargs: Any) -> str:
        endpoint = path.partition("?")[0].rsplit("/", 1)[-1]
        capture_cookie = kwargs.pop("capture_cookie", False)
        kwargs.setdefault("timeout", 10)
        headers = {
            "Accept-Encoding": "identity",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self._base_url}/index.html",
        }
        if path.startswith("/;stok=") and self._cookie:
            headers["Cookie"] = self._cookie
        kwargs.setdefault("headers", headers)
        try:
            response = await self._session.request(
                method, f"{self._base_url}{path}", **kwargs
            )
        except Exception as err:
            _LOGGER.debug("Tenda %s request failed (%s)", endpoint, type(err).__name__)
            # Do not chain the underlying exception: it may contain the stok URL.
            raise TendaConnectionError("Router request failed") from None
        try:
            if response.status >= 400:
                raise TendaConnectionError("Router request failed")
            text = await response.text()
            if capture_cookie and (
                raw_cookie := response.headers.get("Set-Cookie")
            ):
                cookie = raw_cookie.partition(";")[0].strip()
                if cookie.startswith("_:USERNAME:_="):
                    self._cookie = cookie
            return text
        except TendaError:
            raise
        except Exception as err:
            _LOGGER.debug(
                "Tenda %s response read failed (%s)", endpoint, type(err).__name__
            )
            raise TendaConnectionError("Router response could not be read") from None
        finally:
            response.release()


def _decrypt_data(encoded: str, sign: str) -> dict[str, Any]:
    try:
        ciphertext = base64.b64decode(encoded, validate=True)
        decryptor = Cipher(algorithms.AES(sign.encode()), modes.CBC(_IV)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        clear = unpadder.update(padded) + unpadder.finalize()
        value = json.loads(clear.decode())
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise TendaProtocolError("Invalid encrypted response") from None
    if not isinstance(value, dict):
        raise TendaProtocolError("Invalid decrypted response")
    return value


def _encrypt_data(value: dict[str, Any], sign: str) -> str:
    """Encrypt a request payload; retained for future setModules calls."""
    padder = PKCS7(128).padder()
    clear = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
    padded = padder.update(clear) + padder.finalize()
    encryptor = Cipher(algorithms.AES(sign.encode()), modes.CBC(_IV)).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


def parse_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize the HAR-derived module response into stable plain dictionaries."""
    system_raw = _mapping(raw.get("systemCfg"))
    wan_raw = _mapping(raw.get("wanStatus"))
    access_raw = _mapping(raw.get("apModeStatus"))
    work_raw = _mapping(raw.get("workMode"))

    system = {
        "uptime": _integer(system_raw.get("runTime")),
        "model": _text(system_raw.get("productName")),
        "software_version": _text(system_raw.get("softVersion")),
        "hardware_version": _text(system_raw.get("hardVersion")),
        "work_mode": _text(work_raw.get("workMode")),
    }
    wan = {
        "connected": _truthy(wan_raw.get("connectStatus")),
        "internet": _truthy(access_raw.get("isInternet")),
        "download_mbps": _rate_mbps(wan_raw.get("wanDownSpeed")),
        "upload_mbps": _rate_mbps(wan_raw.get("wanUpSpeed")),
        "connection_duration": _integer(wan_raw.get("connectTime")),
        "type": _text(wan_raw.get("wanType")),
    }

    groups = raw.get("deviceList")
    if not isinstance(groups, list):
        groups = raw.get("deviceListNotNeedRate")
    groups = groups if isinstance(groups, list) else []
    groups_by_sn = {
        str(group.get("sn")): group
        for group in groups
        if isinstance(group, dict) and group.get("sn") is not None
    }

    versions = raw.get("deviceVersionList")
    if isinstance(versions, dict):
        versions = next(
            (
                versions[key]
                for key in ("list", "deviceList", "versionList")
                if isinstance(versions.get(key), list)
            ),
            [],
        )
    versions_by_sn = (
        {
            str(item.get("sn")): item
            for item in versions
            if isinstance(item, dict) and item.get("sn") is not None
        }
        if isinstance(versions, list)
        else {}
    )

    nodes: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if not isinstance(value, dict):
            return
        sn = _text(value.get("sn"))
        group = groups_by_sn.get(sn, {})
        version = versions_by_sn.get(sn, {})
        status = _text(value.get("connectStatus"))
        nodes.append(
            {
                "sn": sn,
                "mac": _mac(value.get("nodeMac")),
                "name": _text(value.get("nodeName") or group.get("nodeName")),
                "model": _text(value.get("devModel") or group.get("devModel")),
                "node_type": _text(value.get("nodeType") or group.get("nodeType")),
                "online": _node_online(status),
                "status": status,
                "connection_type": _text(value.get("connectType")),
                "connection_duration": _integer(value.get("connectTime")),
                "client_count": _integer(value.get("clientNum")),
                "firmware": _text(version.get("currentVersion")),
                "hardware_version": _text(version.get("hardVersion")),
            }
        )
        children = value.get("childNode")
        if isinstance(children, list):
            for child in children:
                walk(child)

    topology = raw.get("meshTopo")
    if isinstance(topology, list):
        for root in topology:
            walk(root)
    else:
        walk(topology)

    clients_by_mac: dict[str, dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_sn = _text(group.get("sn"))
        for list_name in ("onlineList", "offlineList", "guestList"):
            entries = group.get(list_name)
            if not isinstance(entries, list):
                continue
            for item in entries:
                if not isinstance(item, dict):
                    continue
                mac = _mac(item.get("mac"))
                if not mac:
                    continue
                access_node = _mapping(item.get("accessNode"))
                connected = list_name != "offlineList" and not _truthy(
                    item.get("offline")
                )
                client = {
                    "mac": mac,
                    "hostname": _text(item.get("hostname")),
                    "ip": _text(item.get("ip")),
                    "connected": connected,
                    "node_sn": _text(access_node.get("sn")) or group_sn,
                    "connection_type": _text(item.get("connectType")),
                    "connection_duration": _integer(item.get("connectTime")),
                    "rssi": _rssi(item.get("rssi")),
                    "upload_kbps": _number(item.get("upSpeed")),
                    "download_kbps": _number(item.get("downSpeed")),
                    "link_rate_mbps": _number(item.get("deviceRate")),
                    "wifi_generation": _integer(item.get("wifiGen")),
                    "guest": list_name == "guestList",
                }
                previous = clients_by_mac.get(mac)
                if previous is None or connected and not previous["connected"]:
                    clients_by_mac[mac] = client

    connected_per_node: dict[str, int] = {}
    for client in clients_by_mac.values():
        if client["connected"] and client["node_sn"]:
            connected_per_node[client["node_sn"]] = (
                connected_per_node.get(client["node_sn"], 0) + 1
            )
    for node in nodes:
        if node["client_count"] is None:
            node["client_count"] = connected_per_node.get(node["sn"], 0)

    return {
        "system": system,
        "wan": wan,
        "nodes": nodes,
        "clients": list(clients_by_mac.values()),
    }


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        raise TendaProtocolError("Invalid JSON response") from None
    if not isinstance(value, dict):
        raise TendaProtocolError("Invalid JSON response")
    return value


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    return str(value) if value is not None and str(value) != "" else None


def _number(value: Any) -> int | float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _rate_mbps(value: Any) -> float | None:
    number = _number(value)
    return round(float(number) / 128, 3) if number is not None else None


def _rssi(value: Any) -> int | None:
    number = _integer(value)
    return number if number not in {None, 0} else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "up",
        "online",
        "connected",
        "good",
        "normal",
        "success",
    }


def _node_online(value: Any) -> bool:
    """The UI treats good, normal and poor links as online."""
    status = str(value).strip().lower() if value is not None else ""
    return bool(status) and status not in {"0", "false", "offline", "disconnected"}


def _mac(value: Any) -> str | None:
    if value is None:
        return None
    compact = re.sub(r"[^0-9A-Fa-f]", "", str(value))
    if len(compact) == 12:
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).lower()
    return str(value).strip().lower() or None


def _is_html(text: str) -> bool:
    start = text.lstrip().lower()
    return start.startswith("<!doctype html") or start.startswith("<html")
