"""Sanitized checks for the local Tenda API client."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "tenda_api", Path(__file__).parents[1] / "custom_components/tenda_be3600/api.py"
)
assert _SPEC and _SPEC.loader
_API = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_API)
TendaApi = _API.TendaApi
TendaLockedError = _API.TendaLockedError
TendaProtocolError = _API.TendaProtocolError
_encrypt_data = _API._encrypt_data
hash_password = _API.hash_password

SIGN = "0123456789ABCDEF"
TOKEN = "a" * 32


class Response:
    def __init__(
        self, body: str, status: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self.body, self.status, self.headers = body, status, headers or {}

    async def text(self) -> str:
        return self.body

    def release(self) -> None:
        pass


class Session:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict]] = []

    async def request(self, method: str, url: str, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0)


def encrypted(raw: dict, sign: str = SIGN) -> Response:
    return Response(json.dumps({"data": _encrypt_data(raw, sign)}))


def fixture() -> dict:
    return {
        "systemCfg": {
            "productName": "Test Mesh",
            "runTime": "3600",
            "softVersion": "V0.test",
            "hardVersion": "test-hw",
        },
        "workMode": {"workMode": "router"},
        "wanStatus": {
            "connectStatus": "connected",
            "wanDownSpeed": "256",
            "wanUpSpeed": 128,
            "connectTime": "60",
            "wanType": "dhcp",
        },
        "apModeStatus": {"isInternet": 1},
        "meshTopo": {
            "sn": "NODE-A",
            "nodeMac": "02-00-00-00-00-01",
            "nodeName": "Main",
            "nodeType": "controller",
            "devModel": "TEST",
            "connectStatus": "good",
            "connectType": "unknow",
            "connectTime": "900",
            "clientNum": 1,
            "childNode": [
                {
                    "sn": "NODE-B",
                    "nodeMac": "02-00-00-00-00-02",
                    "nodeName": "Agent",
                    "nodeType": "agent",
                    "devModel": "TEST",
                    "connectStatus": "poor",
                    "connectType": "wire",
                    "connectTime": 800,
                    "clientNum": 1,
                    "childNode": [],
                }
            ],
        },
        # Deliberately reversed: joins must use SN, never list position.
        "deviceList": [
            {
                "sn": "NODE-B",
                "onlineList": [
                    {
                        "mac": "02-10-00-00-00-02",
                        "hostname": "client-b",
                        "ip": "192.0.2.22",
                        "offline": 0,
                        "connectType": "5G",
                        "rssi": "0",
                        "upSpeed": 4,
                        "downSpeed": 8,
                        "deviceRate": 1201,
                        "wifiGen": 7,
                    }
                ],
                "offlineList": [],
                "guestList": [],
            },
            {
                "sn": "NODE-A",
                "onlineList": [
                    {
                        "mac": "02-10-00-00-00-01",
                        "hostname": "client-a",
                        "ip": "192.0.2.21",
                        "offline": 0,
                        "connectType": "wire",
                        "accessNode": {"sn": "NODE-A"},
                    }
                ],
                "offlineList": [],
                "guestList": [],
            },
        ],
        "deviceVersionList": [
            {"sn": "NODE-B", "currentVersion": "B.1"},
            {"sn": "NODE-A", "currentVersion": "A.1"},
        ],
    }


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_decrypt_and_normalize(self) -> None:
        session = Session(
            [
                Response(json.dumps({"isLocked": False, "leftTimes": 3})),
                Response(
                    json.dumps({"errCode": 0, "sign": SIGN, "stok": TOKEN}),
                    headers={
                        "Set-Cookie": "_:USERNAME:_=opaque-test-value; path=/; httponly"
                    },
                ),
                encrypted(fixture()),
            ]
        )
        digest = hash_password("test-password")
        api = TendaApi(session, "192.0.2.1", digest)
        snapshot = await api.async_get_snapshot()

        self.assertEqual(digest, digest.upper())
        self.assertEqual(session.requests[0][2]["timeout"], 10)
        self.assertEqual(session.requests[1][2]["json"]["password"], digest)
        self.assertIn(f"/;stok={TOKEN}/goform/getModules", session.requests[2][1])
        self.assertEqual(
            session.requests[2][2]["headers"],
            {
                "Accept-Encoding": "identity",
                "Accept-Language": "en-US,en;q=0.9",
                "Cookie": "_:USERNAME:_=opaque-test-value",
                "Referer": "http://192.0.2.1/index.html",
            },
        )
        self.assertEqual(snapshot["wan"]["download_mbps"], 2.0)
        self.assertEqual(snapshot["wan"]["upload_mbps"], 1.0)
        self.assertEqual(
            [node["sn"] for node in snapshot["nodes"]], ["NODE-A", "NODE-B"]
        )
        self.assertEqual(snapshot["nodes"][1]["firmware"], "B.1")
        self.assertTrue(snapshot["nodes"][1]["online"])
        client_b = next(
            client
            for client in snapshot["clients"]
            if client["hostname"] == "client-b"
        )
        self.assertEqual(client_b["node_sn"], "NODE-B")
        self.assertIsNone(client_b["rssi"])

    async def test_expired_html_reauthenticates_once(self) -> None:
        login = lambda: [
            Response(json.dumps({"isLocked": False, "leftTimes": 3})),
            Response(
                json.dumps({"errCode": 0, "sign": SIGN, "stok": TOKEN}),
                headers={"Set-Cookie": "_:USERNAME:_=test-session; path=/"},
            ),
        ]
        session = Session(
            login()
            + [Response("<!DOCTYPE html><html></html>")]
            + login()
            + [encrypted(fixture())]
        )
        snapshot = await TendaApi(
            session, "http://192.0.2.1", hash_password("test")
        ).async_get_snapshot()
        self.assertEqual(snapshot["system"]["uptime"], 3600)
        self.assertEqual(
            sum(url.endswith("/login/Auth") for _, url, _ in session.requests), 2
        )

    async def test_lockout_prevents_password_attempt(self) -> None:
        session = Session([Response(json.dumps({"isLocked": True, "leftTimes": 0}))])
        with self.assertRaises(TendaLockedError):
            await TendaApi(session, "192.0.2.1", hash_password("test")).async_login()
        self.assertEqual(len(session.requests), 1)

    async def test_repeated_session_expiry_is_not_bad_password(self) -> None:
        login = lambda: [
            Response(json.dumps({"isLocked": False, "leftTimes": 3})),
            Response(
                json.dumps({"errCode": 0, "sign": SIGN, "stok": TOKEN}),
                headers={"Set-Cookie": "_:USERNAME:_=test-session; path=/"},
            ),
        ]
        session = Session(
            login()
            + [Response("<!DOCTYPE html><html></html>")]
            + login()
            + [Response("<!DOCTYPE html><html></html>")]
        )
        with self.assertRaises(TendaProtocolError):
            await TendaApi(session, "192.0.2.1", hash_password("test")).async_get_snapshot()


if __name__ == "__main__":
    unittest.main()
