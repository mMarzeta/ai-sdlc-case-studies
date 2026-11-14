from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import urllib.parse
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from vpn_status import VpnStatus, get_vpn_status
from torrent_client import QBittorrentClient, QBittorrentError, TorrentProgress
from config import load_settings


# ---------------------------------------------------------------------------
# Gluetun VPN Status Tests
# ---------------------------------------------------------------------------


def test_vpn_status_connected():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.extensions.get("timeout", {}).get("connect") == 2.0 or request.extensions.get("timeout", {}).get("read") == 2.0
        if request.url.path == "/v1/vpn/status":
            return httpx.Response(200, json={"status": "running"})
        if request.url.path == "/v1/publicip/ip":
            return httpx.Response(200, json={"public_ip": "1.2.3.4", "country": "Switzerland"})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run():
        return await get_vpn_status("http://gluetun:8000", client)

    status = asyncio.run(run())
    assert isinstance(status, VpnStatus)
    assert status.connected is True
    assert status.status_text == "running"
    assert status.public_ip == "1.2.3.4"
    assert status.country == "Switzerland"


def test_vpn_status_legacy_openvpn_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/vpn/status":
            return httpx.Response(404)
        if request.url.path == "/v1/openvpn/status":
            return httpx.Response(200, json={"status": "running"})
        if request.url.path == "/v1/publicip/ip":
            return httpx.Response(200, json={"public_ip": "5.6.7.8", "country": "Poland"})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    status = asyncio.run(get_vpn_status("http://gluetun:8000", client))
    assert status.connected is True
    assert status.public_ip == "5.6.7.8"
    assert status.country == "Poland"


def test_vpn_status_stopped():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/vpn/status":
            return httpx.Response(200, json={"status": "stopped"})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run():
        return await get_vpn_status("http://gluetun:8000", client)

    status = asyncio.run(run())
    assert isinstance(status, VpnStatus)
    assert status.connected is False
    assert status.status_text == "stopped"
    assert status.public_ip is None
    assert status.country is None


def test_vpn_status_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run():
        return await get_vpn_status("http://gluetun:8000", client)

    status = asyncio.run(run())
    assert isinstance(status, VpnStatus)
    assert status.connected is False
    assert "error" in status.status_text.lower() or "connection refused" in status.status_text.lower()
    assert status.public_ip is None
    assert status.country is None


def test_vpn_status_publicip_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/vpn/status":
            return httpx.Response(200, json={"status": "running"})
        if request.url.path == "/v1/publicip/ip":
            return httpx.Response(502, text="Bad Gateway")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run():
        return await get_vpn_status("http://gluetun:8000", client)

    status = asyncio.run(run())
    assert isinstance(status, VpnStatus)
    assert status.connected is False
    assert status.public_ip is None
    assert status.country is None


# ---------------------------------------------------------------------------
# qBittorrent Client Tests
# ---------------------------------------------------------------------------


def test_qbittorrent_login_and_auth_flow():
    login_called = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_called
        if request.url.path == "/api/v2/auth/login":
            login_called += 1
            body = request.read().decode()
            form = urllib.parse.parse_qs(body)
            assert form["username"] == ["admin"]
            assert form["password"] == ["secret123"]
            return httpx.Response(
                200,
                headers={"Set-Cookie": "SID=valid_session_token; Path=/; HttpOnly"},
                text="Ok.",
            )
        if request.url.path == "/api/v2/torrents/info":
            # Verify cookie was sent
            assert "SID=valid_session_token" in request.headers.get("cookie", "")
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient(
        base_url="http://qbittorrent:8085",
        username="admin",
        password="secret123",
        client=client,
    )

    async def run():
        # First request should trigger login automatically
        torrents = await qb.get_torrents(["abc"])
        assert torrents == {}
        # Second request should reuse existing session cookie
        await qb.get_torrents(["abc"])

    asyncio.run(run())
    assert login_called == 1


def test_qbittorrent_login_failure_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Fails.")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient(
        base_url="http://qbittorrent:8085",
        username="admin",
        password="wrong_password",
        client=client,
    )

    async def run():
        with pytest.raises(QBittorrentError, match="[Ll]ogin failed"):
            await qb.get_torrents(["hash1"])

    asyncio.run(run())


def test_qbittorrent_reauth_on_403():
    login_count = 0
    info_call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_count, info_call_count
        if request.url.path == "/api/v2/auth/login":
            login_count += 1
            token = f"session_token_{login_count}"
            return httpx.Response(
                200,
                headers={"Set-Cookie": f"SID={token}; Path=/; HttpOnly"},
                text="Ok.",
            )
        if request.url.path == "/api/v2/torrents/info":
            info_call_count += 1
            # First attempt returns 403 Forbidden to simulate expired session
            if info_call_count == 1:
                return httpx.Response(403, text="Forbidden")
            # Second attempt succeeds
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient(
        base_url="http://qbittorrent:8085",
        username="admin",
        password="password",
        client=client,
    )

    async def run():
        res = await qb.get_torrents(["dummy"])
        assert res == {}

    asyncio.run(run())
    assert login_count == 2
    assert info_call_count == 2


def test_qbittorrent_reauth_failure_raises_after_retry():
    login_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_count
        if request.url.path == "/api/v2/auth/login":
            login_count += 1
            return httpx.Response(
                200,
                headers={"Set-Cookie": f"SID=tok_{login_count}; Path=/; HttpOnly"},
                text="Ok.",
            )
        if request.url.path == "/api/v2/torrents/info":
            return httpx.Response(403, text="Forbidden")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient(
        base_url="http://qbittorrent:8085",
        username="admin",
        password="password",
        client=client,
    )

    async def run():
        with pytest.raises(QBittorrentError, match="403"):
            await qb.get_torrents(["dummy"])

    asyncio.run(run())
    # Initial login + 1 re-auth retry
    assert login_count == 2


def test_qbittorrent_ensure_configured():
    prefs_payload: dict | None = None
    created_categories: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal prefs_payload
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, headers={"Set-Cookie": "SID=tok; Path=/; HttpOnly"}, text="Ok.")
        if request.url.path == "/api/v2/app/setPreferences":
            body = request.read().decode()
            form = urllib.parse.parse_qs(body)
            assert "json" in form
            prefs_payload = json.loads(form["json"][0])
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/torrents/createCategory":
            body = request.read().decode()
            form = urllib.parse.parse_qs(body)
            created_categories.append({k: v[0] for k, v in form.items()})
            # Simulate movies category returning 409 (already present), music returning 200
            if form.get("category") == ["movies"]:
                return httpx.Response(409, text="Category already exists")
            return httpx.Response(200, text="Ok.")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient(
        base_url="http://qbittorrent:8085",
        username="admin",
        password="password",
        client=client,
    )

    async def run():
        await qb.ensure_configured("/downloads", "tun0")

    asyncio.run(run())

    assert prefs_payload is not None
    assert prefs_payload["save_path"] == "/downloads/complete"
    assert prefs_payload["temp_path_enabled"] is True
    assert prefs_payload["temp_path"] == "/downloads/incomplete"
    assert prefs_payload["max_ratio_enabled"] is True
    assert prefs_payload["max_ratio"] == 0.0
    assert prefs_payload["max_ratio_act"] == 0
    assert prefs_payload["current_network_interface"] == "tun0"

    assert len(created_categories) == 2
    cat_names = [c["category"] for c in created_categories]
    assert "movies" in cat_names
    assert "music" in cat_names
    assert created_categories[0]["savePath"] == "/downloads/complete/movies"
    assert created_categories[1]["savePath"] == "/downloads/complete/music"


def test_qbittorrent_add_torrent():
    added_params: dict = {}
    uploaded_content: bytes = b""
    uploaded_filename: str = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal added_params, uploaded_content, uploaded_filename
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, headers={"Set-Cookie": "SID=tok; Path=/; HttpOnly"}, text="Ok.")
        if request.url.path == "/api/v2/torrents/add":
            content_type = request.headers.get("content-type", "")
            assert "multipart/form-data" in content_type
            raw_body = request.read()
            # Inspect body parts
            if b'name="category"' in raw_body:
                added_params["category"] = "movies"
            if b'name="ratioLimit"' in raw_body:
                added_params["ratioLimit"] = "0.0"
            if b'filename="Movie.torrent"' in raw_body:
                uploaded_filename = "Movie.torrent"
            if b"d8:announce" in raw_body:
                uploaded_content = b"d8:announce18:http://tracker/ann4:infod6:lengthi100e4:name5:movieee"
            return httpx.Response(200, text="Ok.")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient(
        base_url="http://qbittorrent:8085",
        username="admin",
        password="password",
        client=client,
    )

    torrent_payload = b"d8:announce18:http://tracker/ann4:infod6:lengthi100e4:name5:movieee"

    async def run():
        await qb.add_torrent(torrent_payload, "Movie.torrent", "movies")

    asyncio.run(run())

    assert added_params.get("category") == "movies"
    assert added_params.get("ratioLimit") == "0.0"
    assert uploaded_filename == "Movie.torrent"
    assert uploaded_content == torrent_payload


def test_qbittorrent_add_torrent_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, headers={"Set-Cookie": "SID=tok; Path=/; HttpOnly"}, text="Ok.")
        if request.url.path == "/api/v2/torrents/add":
            return httpx.Response(200, text="Fails.")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient(
        base_url="http://qbittorrent:8085",
        username="admin",
        password="password",
        client=client,
    )

    async def run():
        with pytest.raises(QBittorrentError, match="[Ff]ails"):
            await qb.add_torrent(b"bad-data", "dummy.torrent", "movies")

    asyncio.run(run())


def test_qbittorrent_get_torrents():
    requested_hashes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, headers={"Set-Cookie": "SID=tok; Path=/; HttpOnly"}, text="Ok.")
        if request.url.path == "/api/v2/torrents/info":
            parsed = urllib.parse.urlparse(str(request.url))
            qs = urllib.parse.parse_qs(parsed.query)
            h = qs.get("hashes", [""])[0]
            requested_hashes.extend(h.split("|"))
            return httpx.Response(
                200,
                json=[
                    {
                        "hash": "4a2b3c4d5e",
                        "state": "downloading",
                        "progress": 0.55,
                        "dlspeed": 1048576,
                        "eta": 120,
                        "content_path": "/downloads/complete/movies/Some.Movie",
                        "size": 524288000,
                    },
                    {
                        "hash": "aabbccddee",
                        "state": "pausedUP",
                        "progress": 1.0,
                        "dlspeed": 0,
                        "eta": 8640000,
                        "content_path": "/downloads/complete/music/Some.Album",
                        "total_size": 104857600,
                    },
                ],
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient(
        base_url="http://qbittorrent:8085",
        username="admin",
        password="password",
        client=client,
    )

    async def run():
        # Empty hashes should return empty without making API calls
        res_empty = await qb.get_torrents([])
        assert res_empty == {}

        res = await qb.get_torrents(["4a2b3c4d5e", "aabbccddee"])
        assert len(res) >= 2
        p1 = res["4a2b3c4d5e"]
        assert isinstance(p1, TorrentProgress)
        assert p1.info_hash == "4a2b3c4d5e"
        assert p1.state == "downloading"
        assert p1.progress == 0.55
        assert p1.dlspeed == 1048576
        assert p1.eta == 120
        assert p1.content_path == "/downloads/complete/movies/Some.Movie"
        assert p1.size == 524288000

        p2 = res["aabbccddee"]
        assert isinstance(p2, TorrentProgress)
        assert p2.info_hash == "aabbccddee"
        assert p2.state == "pausedUP"
        assert p2.progress == 1.0
        assert p2.dlspeed == 0
        assert p2.eta == 8640000
        assert p2.content_path == "/downloads/complete/music/Some.Album"
        assert p2.size == 104857600

    asyncio.run(run())
    assert "4a2b3c4d5e" in requested_hashes
    assert "aabbccddee" in requested_hashes


def test_qbittorrent_delete_torrent():
    deleted_calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, headers={"Set-Cookie": "SID=tok; Path=/; HttpOnly"}, text="Ok.")
        if request.url.path == "/api/v2/torrents/delete":
            body = request.read().decode()
            form = urllib.parse.parse_qs(body)
            deleted_calls.append({k: v[0] for k, v in form.items()})
            return httpx.Response(200, text="Ok.")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient(
        base_url="http://qbittorrent:8085",
        username="admin",
        password="password",
        client=client,
    )

    async def run():
        await qb.delete_torrent("hash1", delete_files=False)
        await qb.delete_torrent("hash2", delete_files=True)

    asyncio.run(run())

    assert len(deleted_calls) == 2
    assert deleted_calls[0] == {"hashes": "hash1", "deleteFiles": "false"}
    assert deleted_calls[1] == {"hashes": "hash2", "deleteFiles": "true"}


def test_qbittorrent_v5_204_login_and_qbt_sid_cookie():
    login_called = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_called
        if request.url.path == "/api/v2/auth/login":
            login_called += 1
            return httpx.Response(
                204,
                headers={"Set-Cookie": "QBT_SID_8085=tok123; Path=/; HttpOnly"},
            )
        if request.url.path == "/api/v2/torrents/info":
            assert "QBT_SID_8085=tok123" in request.headers.get("cookie", "")
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run():
        qb = QBittorrentClient("http://127.0.0.1:8085", "admin", "secret", client=client)
        await qb.get_torrents(["abc"])
        await qb.get_torrents(["def"])

    asyncio.run(run())
    assert login_called == 1


def test_qbittorrent_add_magnet_and_failure():
    add_calls: list[dict[str, str]] = []
    fail_next = False

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, headers={"Set-Cookie": "SID=tok; Path=/; HttpOnly"}, text="Ok.")
        if request.url.path == "/api/v2/torrents/add":
            body = request.read().decode()
            form = urllib.parse.parse_qs(body)
            add_calls.append({k: v[0] for k, v in form.items()})
            return httpx.Response(200, text="Fails." if fail_next else "Ok.")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient("http://qbittorrent:8085", "admin", "password", client=client)
    magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=Movie"

    async def run():
        await qb.add_magnet(magnet, "movies")

    asyncio.run(run())
    assert len(add_calls) == 1
    assert add_calls[0] == {"urls": magnet, "category": "movies", "ratioLimit": "0.0"}

    fail_next = True
    with pytest.raises(QBittorrentError, match="Fails."):
        asyncio.run(qb.add_magnet(magnet, "music"))


def test_qbittorrent_get_torrents_name_and_negative_size_clamped():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, headers={"Set-Cookie": "SID=tok; Path=/; HttpOnly"}, text="Ok.")
        if request.url.path == "/api/v2/torrents/info":
            return httpx.Response(
                200,
                json=[
                    {
                        "hash": "0123456789abcdef0123456789abcdef01234567",
                        "name": "Inception (2010)",
                        "state": "metaDL",
                        "progress": 0.0,
                        "dlspeed": 0,
                        "eta": 8640000,
                        "content_path": "",
                        "size": -1,
                    }
                ],
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    qb = QBittorrentClient("http://qbittorrent:8085", "admin", "password", client=client)

    res = asyncio.run(qb.get_torrents(["0123456789abcdef0123456789abcdef01234567"]))
    prog = res["0123456789abcdef0123456789abcdef01234567"]
    assert prog.name == "Inception (2010)"
    assert prog.size == 0


def test_load_settings_magnet_metadata_timeout(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MAGNET_METADATA_TIMEOUT_SEC", raising=False)
    env_file = tmp_path / ".env"

    env_file.write_text("", encoding="utf-8")
    assert load_settings(env_file).magnet_metadata_timeout_sec == 900

    env_file.write_text("MAGNET_METADATA_TIMEOUT_SEC=120\n", encoding="utf-8")
    assert load_settings(env_file).magnet_metadata_timeout_sec == 120

    env_file.write_text("MAGNET_METADATA_TIMEOUT_SEC=0\n", encoding="utf-8")
    assert load_settings(env_file).magnet_metadata_timeout_sec == 0

    env_file.write_text("MAGNET_METADATA_TIMEOUT_SEC=not-an-int\n", encoding="utf-8")
    assert load_settings(env_file).magnet_metadata_timeout_sec == 900
