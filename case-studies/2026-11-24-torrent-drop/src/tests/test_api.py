import hashlib
import ipaddress
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from config import Settings
from db import JobStore
from vpn_status import VpnStatus
from main import create_app, discover_host_ipv6_subnets, is_allowed_ip


CLIENT_LAN = ("192.0.2.10", 50000)
CLIENT_PUBLIC = ("8.8.8.8", 50000)
CLIENT_V6_LAN = ("::ffff:192.0.2.10", 50000)
CLIENT_V6_PUBLIC = ("::ffff:8.8.8.8", 50000)
CLIENT_V6_GLOBAL = ("2001:4860:4860::8888", 50000)

SAMPLE_INFO_SINGLE = b"d6:lengthi12345e4:name9:Movie.mkv12:piece lengthi16384e6:pieces20:12345678901234567890e"
SAMPLE_TORRENT_SINGLE = b"d8:announce18:http://tracker/ann4:info" + SAMPLE_INFO_SINGLE + b"e"

SAMPLE_INFO_MUSIC = b"d6:lengthi54321e4:name9:Track.mp312:piece lengthi16384e6:pieces20:12345678901234567890e"
SAMPLE_TORRENT_MUSIC = b"d8:announce18:http://tracker/ann4:info" + SAMPLE_INFO_MUSIC + b"e"


@pytest.fixture
def mock_qb():
    qb = MagicMock()
    qb.ensure_configured = AsyncMock(return_value=None)
    qb.add_torrent = AsyncMock(return_value=None)
    qb.add_magnet = AsyncMock(return_value=None)
    qb.delete_torrent = AsyncMock(return_value=None)
    qb.get_torrents = AsyncMock(return_value={})
    qb.aclose = AsyncMock(return_value=None)
    return qb


@pytest.fixture
def vpn_connected():
    return AsyncMock(return_value=VpnStatus(
        connected=True,
        status_text="running",
        public_ip="185.159.157.1",
        country="Switzerland",
    ))


@pytest.fixture
def vpn_disconnected():
    return AsyncMock(return_value=VpnStatus(
        connected=False,
        status_text="stopped",
        public_ip=None,
        country=None,
    ))


@pytest.fixture
def app_and_store(tmp_path: Path, mock_qb, vpn_connected):
    db_file = tmp_path / "test_jobs.db"
    store = JobStore(db_file)
    store.init_schema()

    cfg = Settings(
        app_port=8088,
        db_path=db_file,
        downloads_dir=tmp_path / "downloads",
        movies_dir=tmp_path / "movies",
        music_dir=tmp_path / "music",
    )

    app = create_app(
        cfg=cfg,
        store=store,
        qb=mock_qb,
        vpn_checker=vpn_connected,
        start_worker=False,
    )
    return app, store, mock_qb, vpn_connected


def test_is_allowed_ip_allowed_addresses():
    allowed = [
        "127.0.0.1",
        "::1",
        "192.0.2.10",
        "10.0.0.5",
        "172.16.0.10",
        "100.100.100.100",  # Tailscale CGNAT
        "fd7a:115c:a1e0::1",  # Tailscale IPv6
        "fe80::1",
        "::ffff:192.0.2.10",  # IPv4-mapped IPv6
    ]
    for ip in allowed:
        assert is_allowed_ip(ip) is True, f"Expected {ip} to be allowed"

    # Extra networks support
    extra = [ipaddress.ip_network("2001:db8::/32")]
    assert is_allowed_ip("2001:db8::1", extra) is True
    assert is_allowed_ip("2001:db8::1") is False


def test_is_allowed_ip_rejected_addresses():
    rejected = [
        "8.8.8.8",
        "::ffff:8.8.8.8",
        "2001:4860:4860::8888",
        "testclient",
        "invalid-ip",
        "",
    ]
    for ip in rejected:
        assert is_allowed_ip(ip) is False, f"Expected {ip} to be rejected"


def test_middleware_ip_allowlist(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    # Allowed LAN client
    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.get("/api/status")
        assert resp.status_code == 200

    # Allowed IPv4-mapped IPv6 client
    with TestClient(app, client=CLIENT_V6_LAN) as client:
        resp = client.get("/api/status")
        assert resp.status_code == 200

    # Rejected public IPv4
    with TestClient(app, client=CLIENT_PUBLIC) as client:
        resp = client.get("/api/status")
        assert resp.status_code == 403

    # Rejected IPv4-mapped public IPv6
    with TestClient(app, client=CLIENT_V6_PUBLIC) as client:
        resp = client.get("/api/status")
        assert resp.status_code == 403

    # Rejected public IPv6
    with TestClient(app, client=CLIENT_V6_GLOBAL) as client:
        resp = client.get("/api/status")
        assert resp.status_code == 403

    # Rejects even when X-Forwarded-For is spoofed
    with TestClient(app, client=CLIENT_PUBLIC) as client:
        resp = client.get("/api/status", headers={"X-Forwarded-For": "192.0.2.10"})
        assert resp.status_code == 403


def test_discover_host_ipv6_subnets(monkeypatch):
    # Test real host discovery runs without error
    discovered = discover_host_ipv6_subnets()
    assert isinstance(discovered, list)

    # Test mocked parsing of ip -6 -o addr show scope global
    fake_stdout = (
        "2: eth0    inet6 2001:1b81:1159:c800:601d:3113:c106:2adb/64 scope global dynamic noprefixroute\n"
        "46323: tailscale0    inet6 fd7a:115c:a1e0::5d01:3dd3/128 scope global\n"
        "10: docker0    inet6 2001:db8:1::1/64 scope global\n"
        "11: br-1234    inet6 2001:db8:2::1/64 scope global\n"
        "12: wlan0    inet6 fc00:1234::1/64 scope global\n"  # ULA should be ignored
    )

    class FakeProc:
        returncode = 0
        stdout = fake_stdout

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeProc())
    mocked_nets = discover_host_ipv6_subnets()
    assert mocked_nets == [ipaddress.IPv6Network("2001:1b81:1159:c800::/64")]

    # Test failure returns empty list
    class FailProc:
        returncode = 1
        stdout = ""

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FailProc())
    assert discover_host_ipv6_subnets() == []


def test_get_root_serves_html(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store
    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Torrent Drop" in resp.text
        assert 'id="dropzone"' in resp.text
        assert 'id="vpnBadge"' in resp.text
        assert 'formatSubtitleSummary' in resp.text
        assert 'subs_downloaded' in resp.text
        assert 'imdb_fixed' in resp.text
        assert 'deleteJob(' in resp.text


def test_get_status_endpoint(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    store.create_job(
        info_hash="1111111111111111111111111111111111111111",
        name="Existing.mkv",
        category="movies",
        total_size=1000,
    )

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "vpn" in data
        assert data["vpn"]["connected"] is True
        assert data["vpn"]["public_ip"] == "185.159.157.1"
        assert data["vpn"]["country"] == "Switzerland"
        assert "jobs" in data
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["name"] == "Existing.mkv"


def test_post_torrent_happy_path_movies(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("sample.torrent", SAMPLE_TORRENT_SINGLE, "application/x-bittorrent")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Movie.mkv"
        assert data["category"] == "movies"
        assert data["state"] == "submitted"

        # Verify DB record
        job = store.get_job(data["id"])
        assert job is not None
        assert job.name == "Movie.mkv"
        assert job.category == "movies"
        assert job.state == "submitted"

        # Verify qBittorrent call
        mock_qb.add_torrent.assert_awaited_once_with(
            SAMPLE_TORRENT_SINGLE,
            "sample.torrent",
            "movies",
        )


def test_post_torrent_happy_path_music(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.post(
            "/api/torrents",
            data={"category": "music"},
            files={"file": ("music.torrent", SAMPLE_TORRENT_MUSIC, "application/x-bittorrent")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Track.mp3"
        assert data["category"] == "music"
        mock_qb.add_torrent.assert_awaited_once_with(
            SAMPLE_TORRENT_MUSIC,
            "music.torrent",
            "music",
        )


def test_post_torrent_invalid_category(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.post(
            "/api/torrents",
            data={"category": "games"},
            files={"file": ("sample.torrent", SAMPLE_TORRENT_SINGLE, "application/x-bittorrent")},
        )
        assert resp.status_code in (400, 422)
        assert len(store.list_jobs()) == 0
        mock_qb.add_torrent.assert_not_called()


def test_post_torrent_vpn_disconnected(tmp_path: Path, mock_qb, vpn_disconnected):
    db_file = tmp_path / "test_jobs.db"
    store = JobStore(db_file)
    store.init_schema()
    cfg = Settings(db_path=db_file)

    app = create_app(
        cfg=cfg,
        store=store,
        qb=mock_qb,
        vpn_checker=vpn_disconnected,
        start_worker=False,
    )

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("sample.torrent", SAMPLE_TORRENT_SINGLE, "application/x-bittorrent")},
        )
        assert resp.status_code == 503
        assert len(store.list_jobs()) == 0
        mock_qb.add_torrent.assert_not_called()


def test_post_torrent_duplicate_active_job(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        # First submission succeeds
        resp1 = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("sample.torrent", SAMPLE_TORRENT_SINGLE, "application/x-bittorrent")},
        )
        assert resp1.status_code == 201

        # Second submission while first is still active fails with 409
        resp2 = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("sample.torrent", SAMPLE_TORRENT_SINGLE, "application/x-bittorrent")},
        )
        assert resp2.status_code == 409

        # When first job becomes terminal (done), duplicate submission succeeds
        store.update_job(resp1.json()["id"], state="done")
        resp3 = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("sample.torrent", SAMPLE_TORRENT_SINGLE, "application/x-bittorrent")},
        )
        assert resp3.status_code == 201


def test_post_torrent_malformed_bencode(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("bad.torrent", b"not-a-valid-bencode", "application/x-bittorrent")},
        )
        assert resp.status_code == 400
        assert len(store.list_jobs()) == 0
        mock_qb.add_torrent.assert_not_called()


def test_post_torrent_empty_file(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("empty.torrent", b"", "application/x-bittorrent")},
        )
        assert resp.status_code == 400
        assert len(store.list_jobs()) == 0
        mock_qb.add_torrent.assert_not_called()


def test_post_torrent_oversized_payload(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store
    oversized = b"a" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("big.torrent", oversized, "application/x-bittorrent")},
        )
        assert resp.status_code == 413
        assert len(store.list_jobs()) == 0
        mock_qb.add_torrent.assert_not_called()


def test_delete_job_active(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    # Create active job in DB
    job = store.create_job(
        info_hash="abcdef1234567890abcdef1234567890abcdef12",
        name="ToDelete.mkv",
        category="movies",
        total_size=5000,
    )

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.delete(f"/api/torrents/{job.id}")
        assert resp.status_code == 200

        # Torrent deleted with delete_files=True from client
        mock_qb.delete_torrent.assert_awaited_once_with(job.info_hash, delete_files=True)

        # Removed from SQLite
        assert store.get_job(job.id) is None


def test_delete_job_done_or_failed(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    job = store.create_job(
        info_hash="abcdef1234567890abcdef1234567890abcdef12",
        name="Finished.mkv",
        category="movies",
        total_size=5000,
    )
    store.update_job(job.id, state="done")

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.delete(f"/api/torrents/{job.id}")
        assert resp.status_code == 200

        # Should not call delete_torrent with delete_files=True for finished job
        mock_qb.delete_torrent.assert_not_called()

        # Removed from DB
        assert store.get_job(job.id) is None


def test_delete_job_not_found(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.delete("/api/torrents/999999")
        assert resp.status_code == 404


def test_delete_job_moving_or_post_processing_conflict(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    job = store.create_job(
        info_hash="aabbccddeeff00112233aabbccddeeff00112233",
        name="ActiveMoving.mkv",
        category="movies",
        total_size=5000,
    )
    store.update_job(job.id, state="moving")

    with TestClient(app, client=CLIENT_LAN) as client:
        # Delete while moving -> 409 Conflict
        resp = client.delete(f"/api/torrents/{job.id}")
        assert resp.status_code == 409
        assert "active post-processing" in resp.json()["detail"]
        assert store.get_job(job.id) is not None
        mock_qb.delete_torrent.assert_not_called()

        # Update to post_processing -> 409 Conflict
        store.update_job(job.id, state="post_processing")
        resp = client.delete(f"/api/torrents/{job.id}")
        assert resp.status_code == 409
        assert "active post-processing" in resp.json()["detail"]
        assert store.get_job(job.id) is not None
        mock_qb.delete_torrent.assert_not_called()


def test_upload_qb_configured_retry_success(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        # Manually reset to False to simulate unconfigured state on upload
        app.state.qb_configured = False
        mock_qb.ensure_configured.reset_mock()

        resp = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("sample.torrent", SAMPLE_TORRENT_SINGLE, "application/x-bittorrent")},
        )
        assert resp.status_code == 201
        assert app.state.qb_configured is True
        mock_qb.ensure_configured.assert_awaited_once()


def test_upload_qb_configured_retry_unreachable_returns_503_no_orphan(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        app.state.qb_configured = False
        mock_qb.ensure_configured.side_effect = Exception("Connection refused to qBittorrent")

        resp = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("sample.torrent", SAMPLE_TORRENT_SINGLE, "application/x-bittorrent")},
        )
        assert resp.status_code == 503
        assert "qBittorrent client is unreachable" in resp.json()["detail"]
        assert len(store.list_jobs()) == 0
        assert app.state.qb_configured is False
        mock_qb.add_torrent.assert_not_called()


def test_upload_qb_add_torrent_unexpected_exception_marks_failed(app_and_store):
    app, store, mock_qb, vpn_checker = app_and_store

    with TestClient(app, client=CLIENT_LAN) as client:
        app.state.qb_configured = True
        mock_qb.add_torrent.side_effect = RuntimeError("Generic network socket error")

        resp = client.post(
            "/api/torrents",
            data={"category": "movies"},
            files={"file": ("sample.torrent", SAMPLE_TORRENT_SINGLE, "application/x-bittorrent")},
        )
        assert resp.status_code == 500
        assert "Failed to submit torrent to client" in resp.json()["detail"]

        jobs = store.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].state == "failed"
        assert "Generic network socket error" in (jobs[0].error or "")


def test_create_app_zero_arguments():
    # create_app() must work without arguments for uvicorn main:create_app --factory
    app = create_app()
    assert app is not None
    assert app.title == "torrent-drop" or "torrent" in app.title.lower()


def test_create_dual_stack_socket():
    import socket
    from main import create_dual_stack_socket

    sock = create_dual_stack_socket(0)
    try:
        assert sock.family == socket.AF_INET6
        assert sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 0
    finally:
        sock.close()


def test_submit_magnet_success_and_duplicate_conflict(app_and_store):
    import base64

    app, store, mock_qb, _ = app_and_store
    raw_hash = bytes.fromhex("a1b2c3d4e5f60718293a4b5c6d7e8f9012345678")
    b32_hash = base64.b32encode(raw_hash).decode("ascii")
    magnet_hex = f"magnet:?xt=urn:btih:{raw_hash.hex().upper()}&dn=Dune%20Part%20Two"
    magnet_b32 = f"magnet:?xt=urn:btih:{b32_hash}"

    with TestClient(app, client=CLIENT_LAN) as client:
        resp = client.post("/api/magnets", json={"magnet": magnet_hex, "category": "Movies"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["info_hash"] == raw_hash.hex()
        assert data["name"] == "Dune Part Two"
        assert data["category"] == "movies"
        assert data["total_size"] == 0
        assert data["state"] == "submitted"
        mock_qb.add_magnet.assert_awaited_once_with(magnet_hex, "movies")

        # Submitting same info_hash in base32 returns 409 Conflict
        dup = client.post("/api/magnets", json={"magnet": magnet_b32, "category": "movies"})
        assert dup.status_code == 409


def test_submit_magnet_validation_errors(app_and_store):
    from bencode import MAX_MAGNET_LENGTH

    app, store, mock_qb, _ = app_and_store
    with TestClient(app, client=CLIENT_LAN) as client:
        r_cat = client.post(
            "/api/magnets",
            json={"magnet": "magnet:?xt=urn:btih:" + ("a" * 40), "category": "books"},
        )
        assert r_cat.status_code == 400

        r_bad = client.post(
            "/api/magnets",
            json={"magnet": "https://example.com/not-a-magnet", "category": "movies"},
        )
        assert r_bad.status_code == 400

        r_v2 = client.post(
            "/api/magnets",
            json={"magnet": "magnet:?xt=urn:btmh:1220" + ("ab" * 32), "category": "movies"},
        )
        assert r_v2.status_code == 400
        assert "btmh" in r_v2.json()["detail"]

        r_big = client.post(
            "/api/magnets",
            json={
                "magnet": "magnet:?xt=urn:btih:" + ("a" * 40) + "&dn=" + ("x" * MAX_MAGNET_LENGTH),
                "category": "music",
            },
        )
        assert r_big.status_code == 413
        assert len(store.list_jobs()) == 0
        mock_qb.add_magnet.assert_not_called()


def test_submit_magnet_vpn_down_and_qb_failures(app_and_store):
    app, store, mock_qb, _ = app_and_store
    magnet = "magnet:?xt=urn:btih:" + ("b" * 40) + "&dn=Album"

    with TestClient(app, client=CLIENT_LAN) as client:
        app.state.vpn_checker = AsyncMock(
            return_value=VpnStatus(connected=False, status_text="stopped", public_ip=None, country=None)
        )
        r_vpn = client.post("/api/magnets", json={"magnet": magnet, "category": "music"})
        assert r_vpn.status_code == 503
        assert len(store.list_jobs()) == 0

        app.state.vpn_checker = AsyncMock(
            return_value=VpnStatus(connected=True, status_text="running", public_ip="1.2.3.4", country="PL")
        )
        app.state.qb_configured = False
        mock_qb.ensure_configured.side_effect = Exception("qB offline")
        r_cfg = client.post("/api/magnets", json={"magnet": magnet, "category": "music"})
        assert r_cfg.status_code == 503
        assert len(store.list_jobs()) == 0

        mock_qb.ensure_configured.side_effect = None
        app.state.qb_configured = True
        mock_qb.add_magnet.side_effect = RuntimeError("add magnet boom")
        r_err = client.post("/api/magnets", json={"magnet": magnet, "category": "music"})
        assert r_err.status_code == 500
        jobs = store.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].state == "failed"
        assert "add magnet boom" in (jobs[0].error or "")
