# Local Wi-Fi Proton VPN Torrent Drop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Wi-Fi/Tailscale-only torrent drop web service and VPN-isolated downloader on the Raspberry Pi (`aarch64`) that downloads `.torrent` files strictly through Proton VPN, stops seeding immediately on completion, routes Movies (`jellyfin/media/Movies` + `fix_movies_subtitles_imdb.py`) and Music (`navidrome/music`), and emails completion/failure summaries via Mailgun.

**Architecture:** Two Docker containers (`gluetun` + `qbittorrent` with `network_mode: service:gluetun`) isolate all BitTorrent traffic behind Proton VPN's WireGuard killswitch with Web API ports bound strictly to `127.0.0.1`. A host-side Python 3.13 FastAPI + SQLite service managed by `systemd` (`user=mmarzeta`, `1000:1000`) serves the drag-and-drop UI on dual-stack port `8088`, polls qBittorrent, atomically moves completed payloads on `/dev/nvme0n1p2`, invokes `fix_movies_subtitles_imdb.py --target` on the host (avoiding mounting `/var/run/docker.sock` in containers), and sends Mailgun SMTP notifications.

**Tech Stack:** Docker Compose (`qmcgaw/gluetun:v3`, `lscr.io/linuxserver/qbittorrent:latest`), Python 3.13 (`venv`), FastAPI, Uvicorn, `httpx`, `python-multipart`, SQLite3, `smtplib`, `pytest`, `systemd`.

**Spec:** [2026-11-13-vpn-torrent-drop-design.md](./specs-and-plans/2026-11-13-vpn-torrent-drop-design.md)

## Global Constraints
- Raspberry Pi `aarch64` Debian Linux (`linux/arm64` container images required).
- Containers and host `systemd` service run with UID/GID `1000:1000` (`mmarzeta:mmarzeta`).
- All Gluetun/qBittorrent ports bind strictly to `127.0.0.1` (`127.0.0.1:8085` qBittorrent API, `127.0.0.1:8000` Gluetun control server).
- Host UI listens on dual-stack `::` port `8088` and rejects any non-LAN / non-Tailscale client IP with `403 Forbidden`; never exposed via reverse proxy.
- Zero seeding after completion: `max_ratio=0.0`, `max_ratio_act=0`, and explicit `delete_torrent(delete_files=False)` before moving payload.
- Downloads stage under `~/projects/torrent-drop/downloads/` so moves to `~/projects/jellyfin/media/Movies` and `~/projects/navidrome/music` are atomic on `/dev/nvme0n1p2`; never overwrite existing destinations.
- Corrupted movies reported by `fix_movies_subtitles_imdb.py` must be deleted from `media/Movies`, marked `failed`, and emailed; transient non-corruption subtitle script errors keep the movie in `media/Movies`, mark `done` with a warning, and email.
- Never mount `/var/run/docker.sock` inside any `torrent-drop` container.

## Review Focus
- Malformed, empty, non-bencode, or oversized (`> 10 MB`) `.torrent` uploads: must fail cleanly with HTTP `400`/`413` before creating a SQLite job or touching qBittorrent (pinned in Task 3 and Task 7).
- Spoofed `X-Forwarded-For` headers or IPv4-mapped IPv6 socket addresses (`::ffff:192.0.2.10` vs `::ffff:8.8.8.8`): allowlist middleware must inspect `request.client.host`, ignore forwarding headers, unwrap IPv4-mapped IPv6, and reject public IPs with `403` (pinned in Task 7).
- Re-dropping the same `.torrent` (`info_hash`): must return `409` while an active job exists, but succeed cleanly if the prior job is `failed` or `done` (pinned in Task 2 and Task 7).
- qBittorrent session cookie (`SID`) expiration (`403 Forbidden`) during long downloads: `QBittorrentClient` must re-authenticate once and retry rather than failing the job (pinned in Task 4).
- Single-file vs. multi-file folder payloads for atomic moves and corrupted-video deletion: both file and directory targets must move atomically and delete cleanly without affecting sibling items in `media/Movies` (pinned in Task 1 and Task 6).

---

## File Structure

- Modify: `~/projects/jellyfin/fix_movies_subtitles_imdb.py` — add `--target` and `--json-summary` CLI flags while preserving default full-scan behavior.
- Modify: `~/projects/.gitignore` — ignore `torrent-drop/downloads/`, `torrent-drop/qbittorrent/config/`, `torrent-drop/gluetun/`, `torrent-drop/data/`, `torrent-drop/app/.venv/`.
- Create: `~/projects/torrent-drop/docker-compose.yml` — `gluetun` + `qbittorrent` stack.
- Create: `~/projects/torrent-drop/.env.example` — environment template.
- Create: `~/projects/torrent-drop/torrent-drop.service` — `systemd` unit for host UI + worker.
- Create: `~/projects/torrent-drop/app/pyproject.toml` — Python dependencies and pytest config.
- Create: `~/projects/torrent-drop/app/config.py` — `Settings` loader from `.env`.
- Create: `~/projects/torrent-drop/app/db.py` — SQLite `JobStore` state persistence.
- Create: `~/projects/torrent-drop/app/bencode.py` — `.torrent` bencode parser and SHA-1 `info_hash`.
- Create: `~/projects/torrent-drop/app/vpn_status.py` — Gluetun status/public IP client.
- Create: `~/projects/torrent-drop/app/torrent_client.py` — qBittorrent Web API v2 async client.
- Create: `~/projects/torrent-drop/app/notifier.py` — Mailgun SMTP formatter & sender.
- Create: `~/projects/torrent-drop/app/postprocess.py` — atomic move, `fix_movies_subtitles_imdb.py` runner, corrupted cleanup.
- Create: `~/projects/torrent-drop/app/worker.py` — polling & job state machine loop.
- Create: `~/projects/torrent-drop/app/main.py` — FastAPI app, IP allowlist middleware, routes, lifespan.
- Create: `~/projects/torrent-drop/app/static/index.html` — single-page drag-and-drop UI.
- Create: `~/projects/torrent-drop/tests/test_*.py` — unit and integration test suite.

---

### Task 1: Add `--target` and `--json-summary` to `fix_movies_subtitles_imdb.py`

**Files:**
- Modify: `~/projects/jellyfin/fix_movies_subtitles_imdb.py:157-235,669-707`
- Test: `~/projects/torrent-drop/tests/test_fix_movies_target.py`

**Interfaces:**
- Produces in `~/projects/jellyfin/fix_movies_subtitles_imdb.py`:
  - `discover_target(target: Path, movies_dir: Path, summary: Summary) -> list[MovieItem]`
  - `container_path(host_path: Path, movies_dir: Path = MOVIES_DIR) -> str`
  - CLI flags: `--target PATH` (single file or folder inside `--movies-dir`), `--json-summary` (prints a `JSON_SUMMARY:{...}` line at exit with `Summary` fields serialized via `dataclasses.asdict`).

- [ ] **Step 1: Bootstrap `~/projects/torrent-drop/app/.venv` with `pytest` and write the failing test**

Run:
```bash
mkdir -p ~/projects/torrent-drop/tests ~/projects/torrent-drop/app
python3 -m venv ~/projects/torrent-drop/app/.venv
~/projects/torrent-drop/app/.venv/bin/pip install pytest requests
```

Create `~/projects/torrent-drop/tests/test_fix_movies_target.py`:
```python
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "~/projects/jellyfin")
import fix_movies_subtitles_imdb as fms


def test_discover_target_directory_and_file(tmp_path: Path):
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    other_dir = movies_dir / "Other Movie (2020)"
    other_dir.mkdir()
    (other_dir / "Other.Movie.2020.mkv").write_bytes(b"other")

    target_dir = movies_dir / "Dune Part Two (2024)"
    target_dir.mkdir()
    vid = target_dir / "Dune.Part.Two.2024.1080p.mkv"
    vid.write_bytes(b"video")

    summary = fms.Summary()
    items = fms.discover_target(target_dir, movies_dir, summary)
    assert len(items) == 1
    assert items[0].video_path == vid
    assert items[0].clean_title == "Dune Part Two"
    assert items[0].parsed_year == 2024
    assert fms.container_path(vid, movies_dir) == "/media/Movies/Dune Part Two (2024)/Dune.Part.Two.2024.1080p.mkv"

    single_vid = movies_dir / "Inception.2010.mp4"
    single_vid.write_bytes(b"mp4")
    items_file = fms.discover_target(single_vid, movies_dir, fms.Summary())
    assert len(items_file) == 1
    assert items_file[0].is_root_file is True
    assert items_file[0].video_path == single_vid


def test_cli_target_and_json_summary_dry_run(tmp_path: Path):
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    target_dir = movies_dir / "Arrival (2016)"
    target_dir.mkdir()
    (target_dir / "Arrival.2016.mkv").write_bytes(b"x")
    (target_dir / "Arrival.2016.pol.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHej\n", encoding="utf-8")

    proc = subprocess.run(
        [
            "~/projects/torrent-drop/app/.venv/bin/python",
            "~/projects/jellyfin/fix_movies_subtitles_imdb.py",
            "--dry-run",
            "--movies-dir",
            str(movies_dir),
            "--target",
            str(target_dir),
            "--json-summary",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    json_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("JSON_SUMMARY:")]
    assert len(json_lines) == 1
    payload = json.loads(json_lines[0].removeprefix("JSON_SUMMARY:"))
    assert "corrupted_videos" in payload
    assert "subs_missing" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_fix_movies_target.py -v`
Expected: FAIL with `AttributeError: module 'fix_movies_subtitles_imdb' has no attribute 'discover_target'`.

- [ ] **Step 3: Refactor `discover_movies` into shared file/dir helpers and add `discover_target`, `movies_dir` parameter on `container_path`, and CLI flags in `~/projects/jellyfin/fix_movies_subtitles_imdb.py`**

- Extract `_movie_from_file(entry: Path, root: Path, summary: Summary) -> Optional[MovieItem]` and `_movie_from_dir(entry: Path, summary: Summary) -> Optional[MovieItem]` so `discover_movies` and `discover_target` share one code path.
- Update `container_path(host_path: Path, movies_dir: Path = MOVIES_DIR) -> str` and thread `movies_dir` from `main()` / `process_movie(..., movies_dir: Path = MOVIES_DIR)` so `--movies-dir` works end-to-end.
- Add `--target` (validating `target.resolve().is_relative_to(args.movies_dir.resolve())`, exiting non-zero if missing or outside `--movies-dir`) and `--json-summary` (`print("JSON_SUMMARY:" + json.dumps(asdict(summary)))`).
- Preserve all existing behavior and comments when `--target` and `--json-summary` are omitted.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_fix_movies_target.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git -C ~/projects add jellyfin/fix_movies_subtitles_imdb.py torrent-drop/tests/test_fix_movies_target.py
git -C ~/projects commit -m "feat(jellyfin): add --target and --json-summary to subtitle fixer"
```

---

### Task 2: Project Scaffold, Config, and SQLite Job Store

**Files:**
- Modify: `~/projects/.gitignore`
- Create: `~/projects/torrent-drop/app/pyproject.toml`
- Create: `~/projects/torrent-drop/.env.example`
- Create: `~/projects/torrent-drop/app/config.py`
- Create: `~/projects/torrent-drop/app/db.py`
- Test: `~/projects/torrent-drop/tests/test_db.py`

**Interfaces:**
- Produces in `~/projects/torrent-drop/app/config.py`:
  - `Settings` dataclass with fields: `app_port: int`, `gluetun_url: str`, `qb_url: str`, `qb_user: str`, `qb_password: str`, `qb_interface: str`, `downloads_dir: Path`, `movies_dir: Path`, `music_dir: Path`, `subtitle_script: Path`, `db_path: Path`, `smtp_host: str`, `smtp_port: int`, `smtp_user: str`, `smtp_password: str`, `notify_from: str`, `notify_to: str`, `allowed_subnets: list[str]`, `jellyfin_url: str | None`, `jellyfin_api_key: str | None`
  - `load_settings(env_file: Path | None = None) -> Settings`
- Produces in `~/projects/torrent-drop/app/db.py`:
  - `ACTIVE_STATES = {"submitted", "downloading", "completed_in_client", "moving", "post_processing", "notifying"}`
  - `DuplicateActiveJobError(Exception)`
  - `JobRecord` dataclass (`id: int`, `info_hash: str`, `name: str`, `category: str`, `total_size: int`, `state: str`, `progress: float`, `dlspeed: int`, `eta: int`, `content_path: str | None`, `dest_path: str | None`, `subtitle_summary: str | None`, `warning: str | None`, `error: str | None`, `created_at: str`, `updated_at: str`)
  - `JobStore(db_path: Path)`: `init_schema() -> None`, `create_job(info_hash: str, name: str, category: str, total_size: int) -> JobRecord`, `get_job(job_id: int) -> JobRecord | None`, `list_jobs(limit: int = 50) -> list[JobRecord]`, `list_active_jobs() -> list[JobRecord]`, `update_job(job_id: int, **fields) -> JobRecord`, `delete_job(job_id: int) -> bool`

- [ ] **Step 1: Write `pyproject.toml`, `.env.example`, update `.gitignore`, and write failing `test_db.py`**

Create `~/projects/torrent-drop/app/pyproject.toml` with dependencies (`fastapi`, `uvicorn[standard]`, `httpx`, `python-multipart`, `pytest`) and install them into `~/projects/torrent-drop/app/.venv`.

Create `~/projects/torrent-drop/tests/test_db.py`:
```python
import sys
from pathlib import Path
import pytest

sys.path.insert(0, "~/projects/torrent-drop/app")
from db import DuplicateActiveJobError, JobStore


def test_job_lifecycle_and_duplicate_rules(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.db")
    store.init_schema()

    job = store.create_job("abc123", "Movie.2024", "movies", 1_000_000)
    assert job.state == "submitted"
    assert job.progress == 0.0

    with pytest.raises(DuplicateActiveJobError):
        store.create_job("abc123", "Movie.2024", "movies", 1_000_000)

    updated = store.update_job(job.id, state="downloading", progress=0.5, dlspeed=2048)
    assert updated.state == "downloading"
    assert updated.progress == 0.5
    assert len(store.list_active_jobs()) == 1

    store.update_job(job.id, state="failed", error="corrupted video")
    assert len(store.list_active_jobs()) == 0

    requeued = store.create_job("abc123", "Movie.2024", "movies", 1_000_000)
    assert requeued.id != job.id
    assert len(store.list_jobs()) == 2
    assert store.delete_job(job.id) is True
    assert store.get_job(job.id) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db'`.

- [ ] **Step 3: Implement `config.py` and `db.py` in `~/projects/torrent-drop/app/`**

- `config.py`: parses `.env` (if present) and `os.environ` into `Settings` with spec defaults (`~/projects/torrent-drop/downloads`, `~/projects/jellyfin/media/Movies`, `~/projects/navidrome/music`, `~/projects/jellyfin/fix_movies_subtitles_imdb.py`, `smtp.eu.mailgun.org`, `587`, `127.0.0.1:8085`, `127.0.0.1:8000`, `APP_PORT=8088`).
- `db.py`: uses `sqlite3` with WAL mode and a `threading.Lock` (or short-lived connections per method), partial/active duplicate check (`SELECT id FROM jobs WHERE info_hash = ? AND state IN (...)`), and `JobRecord` hydration.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_db.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C ~/projects add .gitignore torrent-drop/.env.example torrent-drop/app/pyproject.toml torrent-drop/app/config.py torrent-drop/app/db.py torrent-drop/tests/test_db.py
git -C ~/projects commit -m "feat(torrent-drop): add config loader and sqlite job store"
```

---

### Task 3: `.torrent` Bencode Parser & Validator

**Files:**
- Create: `~/projects/torrent-drop/app/bencode.py`
- Test: `~/projects/torrent-drop/tests/test_bencode.py`

**Interfaces:**
- Produces in `~/projects/torrent-drop/app/bencode.py`:
  - `TorrentParseError(ValueError)`
  - `TorrentMeta` dataclass (`info_hash: str`, `name: str`, `total_size: int`)
  - `parse_torrent_bytes(data: bytes) -> TorrentMeta`

- [ ] **Step 1: Write failing `test_bencode.py` (including single-file, multi-file, exact SHA-1 `info_hash`, and malformed/empty inputs)**

Create `~/projects/torrent-drop/tests/test_bencode.py`:
```python
import hashlib
import sys
import pytest

sys.path.insert(0, "~/projects/torrent-drop/app")
from bencode import TorrentParseError, parse_torrent_bytes


def test_parse_single_and_multi_file_torrent():
    info_single = b"d6:lengthi12345e4:name9:Movie.mkv12:piece lengthi16384e6:pieces20:12345678901234567890e"
    torrent_single = b"d8:announce20:http://tracker/ann4:info" + info_single + b"e"
    meta = parse_torrent_bytes(torrent_single)
    assert meta.info_hash == hashlib.sha1(info_single).hexdigest()
    assert meta.name == "Movie.mkv"
    assert meta.total_size == 12345

    info_multi = b"d5:filesld6:lengthi100e4:pathl7:cd1.mp3eed6:lengthi250e4:pathl7:cd2.mp3eee4:name5:Album12:piece lengthi16384e6:pieces20:12345678901234567890e"
    torrent_multi = b"d4:info" + info_multi + b"e"
    meta_m = parse_torrent_bytes(torrent_multi)
    assert meta_m.info_hash == hashlib.sha1(info_multi).hexdigest()
    assert meta_m.name == "Album"
    assert meta_m.total_size == 350


@pytest.mark.parametrize("bad", [b"", b"not-bencode", b"l4:teste", b"d8:announce4:teste", b"d4:infod6:lengthi10eee"])
def test_parse_invalid_torrent_raises(bad: bytes):
    with pytest.raises(TorrentParseError):
        parse_torrent_bytes(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_bencode.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bencode'`.

- [ ] **Step 3: Implement `bencode.py`**

Implement a ~60-line bencode decoder that records the exact byte `[start:end]` span of the `info` dictionary value so `hashlib.sha1(data[info_start:info_end]).hexdigest()` matches the BitTorrent spec identically regardless of key types, validates `name` (UTF-8 with replacement fallback) and `length`/`files` total size, and raises `TorrentParseError` on any structural or trailing-garbage error.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_bencode.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C ~/projects add torrent-drop/app/bencode.py torrent-drop/tests/test_bencode.py
git -C ~/projects commit -m "feat(torrent-drop): add bencode parser and info_hash extractor"
```

---

### Task 4: Gluetun VPN Status & qBittorrent Web API Client

**Files:**
- Create: `~/projects/torrent-drop/app/vpn_status.py`
- Create: `~/projects/torrent-drop/app/torrent_client.py`
- Test: `~/projects/torrent-drop/tests/test_clients.py`

**Interfaces:**
- Produces in `~/projects/torrent-drop/app/vpn_status.py`:
  - `VpnStatus` dataclass (`connected: bool`, `status_text: str`, `public_ip: str | None`, `country: str | None`)
  - `async def get_vpn_status(gluetun_url: str, client: httpx.AsyncClient) -> VpnStatus`
- Produces in `~/projects/torrent-drop/app/torrent_client.py`:
  - `QBittorrentError(RuntimeError)`
  - `TorrentProgress` dataclass (`info_hash: str`, `state: str`, `progress: float`, `dlspeed: int`, `eta: int`, `content_path: str`, `size: int`)
  - `QBittorrentClient(base_url: str, username: str, password: str, client: httpx.AsyncClient | None = None)`:
    - `async def ensure_configured(self, downloads_dir: str, network_interface: str) -> None`
    - `async def add_torrent(self, torrent_bytes: bytes, filename: str, category: str) -> None`
    - `async def get_torrents(self, hashes: list[str]) -> dict[str, TorrentProgress]`
    - `async def delete_torrent(self, info_hash: str, delete_files: bool = False) -> None`

- [ ] **Step 1: Write failing `test_clients.py`**

Test using `httpx.MockTransport`:
1. `get_vpn_status`: returns `connected=True` with IP and country when `/v1/openvpn/status` returns `{"status":"running"}` and `/v1/publicip/ip` returns `{"public_ip":"1.2.3.4","country":"Switzerland"}`; returns `connected=False` on stopped status or connection error.
2. `QBittorrentClient`: logs in via `/api/v2/auth/login`, re-authenticates once automatically when an API call returns `403`, sends `ratioLimit=0.0` + `category=movies` on `add_torrent`, sets `max_ratio_enabled=True`, `max_ratio=0.0`, `max_ratio_act=0`, `current_network_interface` in `ensure_configured`, and passes `deleteFiles=false` on `delete_torrent`.

- [ ] **Step 2: Run test to verify it fails**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_clients.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `vpn_status.py` and `torrent_client.py`**

- `vpn_status.py`: queries `GET {gluetun_url}/v1/openvpn/status` (Gluetun uses this endpoint for both OpenVPN and WireGuard tunnel status) and `GET {gluetun_url}/v1/publicip/ip` with short 2s timeouts; catches `httpx.HTTPError` cleanly to return `VpnStatus(connected=False, ...)`.
- `torrent_client.py`: wraps `httpx.AsyncClient` with cookie persistence and a `_request()` helper that logs in on missing cookie or single `403` retry; creates `movies` (`/downloads/complete/movies`) and `music` (`/downloads/complete/music`) categories via `/api/v2/torrents/createCategory` (ignoring `409` if already present).

- [ ] **Step 4: Run test to verify it passes**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_clients.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C ~/projects add torrent-drop/app/vpn_status.py torrent-drop/app/torrent_client.py torrent-drop/tests/test_clients.py
git -C ~/projects commit -m "feat(torrent-drop): add gluetun status and qbittorrent api clients"
```

---

### Task 5: Mailgun SMTP Notifier

**Files:**
- Create: `~/projects/torrent-drop/app/notifier.py`
- Test: `~/projects/torrent-drop/tests/test_notifier.py`

**Interfaces:**
- Consumes: `Settings` (`config.py`), `JobRecord` (`db.py`).
- Produces in `~/projects/torrent-drop/app/notifier.py`:
  - `format_completion_email(job: JobRecord, subtitle_summary: dict | None, warning: str | None = None) -> tuple[str, str]`
  - `format_failure_email(job: JobRecord) -> tuple[str, str]`
  - `send_email(cfg: Settings, subject: str, body: str) -> None`

- [ ] **Step 1: Write failing `test_notifier.py`**

Verify:
- `format_completion_email` for Movies includes title, size, destination path, IMDb/Polish subtitle counts/outcomes, and any warning text.
- `format_completion_email` for Music includes destination path under `navidrome/music`.
- `format_failure_email` includes failure stage/reason (`job.error`).
- `send_email` connects to `cfg.smtp_host:cfg.smtp_port`, calls `starttls()`, `login()`, and `send_message()`.

- [ ] **Step 2: Run test to verify it fails**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_notifier.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `notifier.py`**

Use `email.message.EmailMessage` and `smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30)` with `starttls()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_notifier.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C ~/projects add torrent-drop/app/notifier.py torrent-drop/tests/test_notifier.py
git -C ~/projects commit -m "feat(torrent-drop): add Mailgun SMTP notification formatter and sender"
```

---

### Task 6: Post-Processor & Background Worker State Machine

**Files:**
- Create: `~/projects/torrent-drop/app/postprocess.py`
- Create: `~/projects/torrent-drop/app/worker.py`
- Test: `~/projects/torrent-drop/tests/test_postprocess_worker.py`

**Interfaces:**
- Consumes: `Settings` (`config.py`), `JobStore`, `JobRecord` (`db.py`), `QBittorrentClient` (`torrent_client.py`), `send_email`, `format_completion_email`, `format_failure_email` (`notifier.py`).
- Produces in `~/projects/torrent-drop/app/postprocess.py`:
  - `PostProcessError(RuntimeError)`
  - `CorruptedVideoError(PostProcessError)`
  - `map_container_path(content_path: str, downloads_dir: Path) -> Path`
  - `move_to_library(src_path: Path, dest_dir: Path) -> Path`
  - `cleanup_target(path: Path) -> None`
  - `run_subtitle_script(script_path: Path, target_path: Path, movies_dir: Path, timeout_sec: int = 300) -> tuple[dict | None, str | None]`
- Produces in `~/projects/torrent-drop/app/worker.py`:
  - `async def poll_once(store: JobStore, qb: QBittorrentClient, cfg: Settings) -> None`
  - `async def run_worker_loop(store: JobStore, qb: QBittorrentClient, cfg: Settings, stop_event: asyncio.Event, interval_sec: float = 3.0) -> None`

- [ ] **Step 1: Write failing `test_postprocess_worker.py`**

Cover all 5 critical flows:
1. Single-file `.mkv` and directory Movie happy path: `progress=1.0` + `pausedUP` -> `delete_torrent(hash, delete_files=False)` -> moved atomically to `movies_dir` -> `run_subtitle_script` invoked -> `state == "done"` -> completion email sent.
2. Music happy path: moved to `music_dir`, subtitle script NOT called, `state == "done"`, completion email sent.
3. Destination collision: existing folder/file in `movies_dir` is NOT overwritten; job becomes `failed`, failure email sent, staging copy left intact.
4. Corrupted video reported by subtitle script (`corrupted_videos` non-empty): moved file/directory in `movies_dir` is deleted (`cleanup_target`), sibling movies untouched, job becomes `failed`, failure email sent.
5. Transient subtitle script crash/non-zero exit without `corrupted_videos`: movie stays in `movies_dir`, job becomes `done` with `warning` set, completion email sent including warning.

- [ ] **Step 2: Run test to verify it fails**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_postprocess_worker.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `postprocess.py` and `worker.py`**

- `map_container_path`: validates `content_path` starts with `/downloads/` and resolves safely inside `downloads_dir` (rejecting path traversal).
- `move_to_library`: checks `dest = dest_dir / src_path.name`; raises `PostProcessError` if `dest.exists()`; creates `dest_dir` if needed; calls `shutil.move(str(src_path), str(dest))`.
- `run_subtitle_script`: runs `asyncio.create_subprocess_exec(sys.executable, str(script_path), "--movies-dir", str(movies_dir), "--target", str(target_path), "--json-summary")` with timeout; parses `JSON_SUMMARY:` line; raises `CorruptedVideoError` if `summary["corrupted_videos"]` is non-empty; returns `(summary, warning_str)` on non-zero exit/timeout when no corruption was reported.
- `worker.py`: drives `submitted`/`downloading` jobs through completion; wraps blocking `send_email` in `asyncio.to_thread`; catches exceptions per job so one broken job never stalls the polling loop.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_postprocess_worker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C ~/projects add torrent-drop/app/postprocess.py torrent-drop/app/worker.py torrent-drop/tests/test_postprocess_worker.py
git -C ~/projects commit -m "feat(torrent-drop): add post-processor and background worker loop"
```

---

### Task 7: FastAPI Web UI, LAN/Tailscale IP Allowlist, and Endpoints

**Files:**
- Create: `~/projects/torrent-drop/app/main.py`
- Create: `~/projects/torrent-drop/app/static/index.html`
- Test: `~/projects/torrent-drop/tests/test_api.py`

**Interfaces:**
- Consumes: `Settings` (`config.py`), `JobStore` (`db.py`), `parse_torrent_bytes` (`bencode.py`), `get_vpn_status` (`vpn_status.py`), `QBittorrentClient` (`torrent_client.py`), `run_worker_loop` (`worker.py`).
- Produces in `~/projects/torrent-drop/app/main.py`:
  - `is_allowed_ip(ip_str: str, extra_nets: list[ipaddress._BaseNetwork]) -> bool`
  - `create_app(cfg: Settings | None = None, store: JobStore | None = None, qb: QBittorrentClient | None = None, vpn_checker: Callable | None = None, start_worker: bool = True) -> FastAPI`
  - Endpoints: `GET /`, `GET /api/status`, `POST /api/torrents`, `DELETE /api/torrents/{job_id}`

- [ ] **Step 1: Write failing `test_api.py`**

Verify:
1. `is_allowed_ip` & middleware:
   - Allows `127.0.0.1`, `::1`, `192.0.2.10`, `10.0.0.5`, `172.16.0.10`, `100.100.100.100` (Tailscale CGNAT), `fd7a:115c:a1e0::1` (Tailscale IPv6), `fe80::1`, `::ffff:192.0.2.10`.
   - Rejects `8.8.8.8`, `::ffff:8.8.8.8`, `2001:4860:4860::8888` with `403 Forbidden`, even when `X-Forwarded-For: 192.0.2.10` is sent.
2. `POST /api/torrents`:
   - Valid `.torrent` + `category=movies` when VPN connected -> `201`, job created, `qb.add_torrent` called.
   - VPN disconnected -> `503`.
   - Active duplicate `info_hash` -> `409`.
   - Malformed `.torrent` bytes -> `400`; payload `> 10 MB` -> `413`.
3. `GET /api/status` returns VPN status + job list; `DELETE /api/torrents/{id}` deletes active torrent with `delete_files=True` and removes DB row.

- [ ] **Step 2: Run test to verify it fails**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `main.py` and `static/index.html`**

- `main.py`: discovers active non-loopback IPv6 `/64` prefixes on the host via `ip -6 -o addr show scope global` at startup (best-effort, ignoring Tailscale/global-if-disabled or using `ALLOWED_SUBNETS` override) + RFC1918 + loopback + Tailscale (`100.64.0.0/10`, `fd7a:115c:a1e0::/48`) + IPv6 ULA/link-local (`fc00::/7`, `fe80::/10`). Unwraps `IPv6Address.ipv4_mapped` before network check.
- `static/index.html`: clean responsive single-page app (vanilla HTML/CSS/JS, zero build tools):
  - Top VPN badge (`Connected · <country> · <ip>` or red `Disconnected` alert).
  - **Movie** / **Music** segmented toggle (Movie default).
  - Drag-and-drop zone + click-to-browse `.torrent` picker.
  - Auto-refreshing job table every 3s showing title, category badge, state, progress bar, speed/ETA, subtitle/IMDb summary or error, and Cancel/Remove button.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C ~/projects add torrent-drop/app/main.py torrent-drop/app/static/index.html torrent-drop/tests/test_api.py
git -C ~/projects commit -m "feat(torrent-drop): add FastAPI drop UI, API, and LAN/Tailscale IP guard"
```

---

### Task 8: Docker Compose, `systemd` Service, and Full Verification

**Files:**
- Create: `~/projects/torrent-drop/docker-compose.yml`
- Create: `~/projects/torrent-drop/torrent-drop.service`

- [ ] **Step 1: Create `~/projects/torrent-drop/docker-compose.yml` and `torrent-drop.service`**

- `docker-compose.yml`:
  - `gluetun` (`qmcgaw/gluetun:v3`, `cap_add: [NET_ADMIN]`, `devices: [/dev/net/tun:/dev/net/tun]`, `VPN_SERVICE_PROVIDER=protonvpn`, `VPN_TYPE=wireguard`, `127.0.0.1:8085:8085`, `127.0.0.1:8000:8000`, `healthcheck` using `/gluetun-entrypoint healthcheck`, `restart: unless-stopped`).
  - `qbittorrent` (`lscr.io/linuxserver/qbittorrent:latest`, `network_mode: "service:gluetun"`, `depends_on: gluetun: condition: service_healthy`, `PUID=1000`, `PGID=1000`, `TZ=Europe/Warsaw`, `WEBUI_PORT=8085`, volumes `./qbittorrent/config:/config` and `./downloads:/downloads`, `restart: unless-stopped`).
- `torrent-drop.service`:
  - `User=mmarzeta`, `Group=mmarzeta`, `WorkingDirectory=~/projects/torrent-drop/app`, `ExecStart=~/projects/torrent-drop/app/.venv/bin/uvicorn main:create_app --factory --host :: --port 8088`, `After=docker.service network-online.target`, `Restart=always`.

- [ ] **Step 2: Validate Compose syntax and run full `pytest` suite**

Run:
```bash
docker compose -f ~/projects/torrent-drop/docker-compose.yml config --quiet
~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests -v
```
Expected: Compose exits `0` and all tests in `tests/` PASS.

- [ ] **Step 3: Populate `.env` with Proton VPN WireGuard + Mailgun credentials, start stack, and verify VPN killswitch**

Manual deployment / smoke check commands (once `.env` is populated from Proton VPN account & `~/projects/.env`):
```bash
docker compose -f ~/projects/torrent-drop/docker-compose.yml up -d
# Verify qBittorrent container exits through Proton VPN IP (not host IP):
docker exec qbittorrent curl -fsS https://ipinfo.io/ip
# Install and start systemd unit:
sudo cp ~/projects/torrent-drop/torrent-drop.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now torrent-drop.service
curl -fsS http://127.0.0.1:8088/api/status
```

- [ ] **Step 4: Commit**

```bash
git -C ~/projects add torrent-drop/docker-compose.yml torrent-drop/torrent-drop.service
git -C ~/projects commit -m "feat(torrent-drop): add gluetun/qbittorrent compose stack and systemd unit"
```
