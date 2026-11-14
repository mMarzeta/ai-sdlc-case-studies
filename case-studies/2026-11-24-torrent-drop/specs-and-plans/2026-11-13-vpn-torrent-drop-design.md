# Design Doc: Local Wi-Fi Proton VPN Torrent Drop Downloader

## Intent & The Why
Provide a zero-friction way to download movies and music from a Raspberry Pi (`aarch64`) over local home Wi-Fi using a Proton VPN Premium account. The user drops a `.torrent` file into a clean local web UI, chooses **Movie** or **Music**, and receives an email once the download completes, lands in the right media library, and (for movies) finishes IMDb/subtitle verification. All BitTorrent traffic must stay strictly inside the VPN tunnel with a hard killswitch and zero post-download seeding.

## Goals
1. **Simple Wi-Fi-only Web UI:** Drag-and-drop `.torrent` upload with a **Movie** / **Music** selector, live Proton VPN status indicator, and download/post-processing job status history.
2. **Strict VPN Isolation & Killswitch:** All BitTorrent, tracker, and DHT traffic runs inside a dedicated VPN network namespace (`gluetun` + `qbittorrent`), dropping all egress if Proton VPN disconnects. Other Raspberry Pi services (`jellyfin`, `pihole`, `gitea`, `ghost`, `navidrome`, etc.) remain untouched on the normal host network.
3. **Zero Seeding:** Torrents are stopped and removed from the client immediately upon reaching 100% completion (`ratio = 0`), without deleting downloaded payload files.
4. **Automatic Media Routing:**
   - **Movies** move atomically to `~/projects/jellyfin/media/Movies` and trigger `~/projects/jellyfin/fix_movies_subtitles_imdb.py` scoped to the newly added movie.
   - **Music** moves atomically to `~/projects/navidrome/music`.
5. **Email Notifications:** Send completion and failure emails via the existing Mailgun SMTP setup (`smtp.eu.mailgun.org:587`), including IMDb and Polish subtitle outcomes for movies.

## Non-Goals
- Public internet exposure, reverse-proxy publishing, or multi-user authentication (access is restricted to local Wi-Fi/LAN).
- Seeding management, private-tracker ratio rules, or scheduled bandwidth throttling.
- Automated TV Show (`media/Shows`) episode/season sorting in v1.
- Torrent search/indexer integration (e.g., Prowlarr, Radarr, Sonarr).

## Anti-Goals
- **IP Leakage:** Any BitTorrent traffic leaving the Raspberry Pi outside the Proton VPN tunnel during tunnel drops, container restarts, or DNS lookups.
- **Partial File Ingestion:** Moving incomplete downloads into `jellyfin/media/Movies` or `navidrome/music` (completion must come from torrent client state, not folder-polling heuristics).
- **Host VPN Routing:** Running Proton VPN at the Raspberry Pi OS level where it would disrupt Jellyfin, Pi-hole, Gitea, Ghost, or SSH.
- **Weakening Container Isolation:** Mounting `/var/run/docker.sock` inside the VPN or torrent container.

## Environment & Constraints (Observed on `raspberrypi`)
- **Host:** Raspberry Pi `aarch64` Debian Linux; containers must support `linux/arm64`.
- **Storage:** `~/projects` resides on a single NVMe partition (`/dev/nvme0n1p2`, 288 GB available). Placing the download staging directory under `~/projects/torrent-drop/downloads` guarantees atomic, instant `rename()` moves into `jellyfin/media/Movies` and `navidrome/music`.
- **Permissions:** Existing media containers run as `1000:1000` (`mmarzeta:mmarzeta`), and `mmarzeta` belongs to the `docker` group.
- **Subtitle Script:** `~/projects/jellyfin/fix_movies_subtitles_imdb.py` runs on the host and invokes `docker exec jellyfin /usr/lib/jellyfin-ffmpeg/{ffprobe,ffmpeg}`, mapping paths relative to `~/projects/jellyfin/media/Movies`.
- **Email:** Mailgun SMTP (`smtp.eu.mailgun.org:587`) is already used in `~/projects/docker-compose.yml` (`GITEA_MAILGUN_PASSWD` / `GHOST_MAILGUN_PASSWD` in `.env`, recipient `contact@marzeta.pl`).

## Approaches Considered
1. **Approach A: Gluetun + Headless qBittorrent + Custom Host Drop UI & Worker (Selected)**
   - *Design:* `gluetun` owns the Proton VPN tunnel and `iptables` killswitch; `qbittorrent` shares `gluetun`'s network namespace (`network_mode: service:gluetun`) with its WebUI bound only to `127.0.0.1`. A lightweight FastAPI + SQLite service runs on the host via `systemd` as user `mmarzeta`, serving the LAN-only drop UI, polling qBittorrent, performing atomic moves, invoking `fix_movies_subtitles_imdb.py`, and sending Mailgun emails.
   - *Trade-off:* Adds a small custom Python app (~300–500 lines), in exchange for an exact drop-and-forget UX, rock-solid container killswitch isolation, and clean host execution of `fix_movies_subtitles_imdb.py` without exposing `docker.sock` to containers.
2. **Approach B: Gluetun + qBittorrent Built-in WebUI + Completion Hook**
   - *Trade-off:* Zero custom UI code, but exposes qBittorrent's cluttered WebUI instead of a simple drop page and complicates running `docker exec jellyfin` from inside the isolated container.
3. **Approach C: Custom `libtorrent` Python App inside a Linux `netns`**
   - *Trade-off:* Single codebase, but requires maintaining brittle host-level `ip netns` / `nftables` killswitch and DNS leak rules instead of using Gluetun's proven implementation.

## Detailed Design

### 1. Directory & Deployment Layout
All files live under `~/projects/torrent-drop/`, matching the per-project layout used by `jellyfin/`:
```text
~/projects/torrent-drop/
├── docker-compose.yml          # gluetun + qbittorrent containers
├── .env                        # Proton VPN creds, qBittorrent creds, Mailgun SMTP (gitignored)
├── .env.example                # Documented template
├── gluetun/                    # Gluetun persistent state (if needed)
├── qbittorrent/config/         # qBittorrent configuration
├── downloads/
│   ├── incomplete/             # Active downloads
│   └── complete/
│       ├── movies/             # Completed Movie torrents awaiting move
│       └── music/              # Completed Music torrents awaiting move
└── app/
    ├── pyproject.toml / requirements.txt
    ├── main.py                 # FastAPI web UI + API + background worker loop
    ├── torrent_client.py       # qBittorrent Web API v2 wrapper
    ├── vpn_status.py           # Gluetun control server health/IP check
    ├── postprocess.py          # Atomic move + fix_movies_subtitles_imdb.py runner
    ├── notifier.py             # Mailgun SMTP sender
    ├── db.py                   # SQLite job store (./data/jobs.db)
    └── static/index.html       # Single-page drag-and-drop UI
```
*My call:* Run the FastAPI + worker app directly on the host as a `systemd` service (`torrent-drop.service`) under user `mmarzeta` (`1000:1000`) rather than inside Docker, so it can atomically move files and call `fix_movies_subtitles_imdb.py` (which uses `docker exec jellyfin`) without mounting `/var/run/docker.sock` into any container.

### 2. VPN & Torrent Engine (`docker-compose.yml`)
- **`gluetun` (`qmcgaw/gluetun:v3`):**
  - `cap_add: [NET_ADMIN]`, `devices: [/dev/net/tun:/dev/net/tun]`
  - *My call:* Default to **WireGuard** (`VPN_SERVICE_PROVIDER=protonvpn`, `VPN_TYPE=wireguard`, `WIREGUARD_PRIVATE_KEY`, `WIREGUARD_ADDRESSES`, and P2P server selection via `SERVER_COUNTRIES` or `SERVER_HOSTNAMES` from the user's Proton VPN Premium WireGuard config). WireGuard uses substantially less CPU on Raspberry Pi and recovers faster than OpenVPN; since seeding is disabled, NAT-PMP port forwarding is optional (though OpenVPN + `VPN_PORT_FORWARDING=on` remains a drop-in env change if ever needed).
  - Killswitch & DNS: Gluetun's firewall blocks all non-tunnel outbound traffic by default; DNS resolves through the tunnel.
  - Published ports bound strictly to loopback (`127.0.0.1`):
    - `127.0.0.1:8085:8085` (qBittorrent Web API for the host worker only)
    - `127.0.0.1:8000:8000` (Gluetun HTTP control server for VPN status/public IP checks)
  - Built-in Gluetun healthcheck enabled (`interval: 15s`, `retries: 3`).
- **`qbittorrent` (`lscr.io/linuxserver/qbittorrent:latest`):**
  - `network_mode: "service:gluetun"`
  - `depends_on: gluetun: condition: service_healthy`
  - `PUID=1000`, `PGID=1000`, `TZ=Europe/Warsaw`, `WEBUI_PORT=8085`
  - Volumes: `./qbittorrent/config:/config`, `./downloads:/downloads`
  - Enforced settings on startup via Web API (`/api/v2/app/setPreferences`):
    - `save_path`: `/downloads/complete`, `temp_path_enabled`: `true`, `temp_path`: `/downloads/incomplete`
    - Categories `movies` (`/downloads/complete/movies`) and `music` (`/downloads/complete/music`)
    - `max_ratio_enabled`: `true`, `max_ratio`: `0.0`, `max_ratio_act`: `0` (pause on completion)
    - `network_interface`: `tun0` (or `wg0` for WireGuard) as a secondary belt-and-suspenders bind guard inside qBittorrent.

### 3. Host Web UI & API (`app/main.py`)
- **Network Restriction (Wi-Fi / LAN & Tailscale):**
  - Listens on `::` (dual-stack `0.0.0.0` + IPv6) port `8088` (configurable via `APP_PORT`).
  - Middleware enforces a private/local allowlist (`403 Forbidden` otherwise):
    - Loopback: `127.0.0.0/8`, `::1/128`
    - LAN IPv4 (RFC1918): `10.0.0.0/8`, `172.16.0.0/12`, `192.0.2.10/16`
    - Tailscale: `100.64.0.0/10` and `fd7a:115c:a1e0::/48`
    - IPv6 LAN: `fe80::/10`, `fc00::/7`, plus any non-loopback `/64` interface prefix currently assigned to the Pi's LAN NIC (`eth0`/`wlan0`, discovered at startup or configured via `ALLOWED_SUBNETS`) so local IPv6 SLAAC devices work without exposing the port to the public internet.
  - Not added to any external reverse proxy.
- **UI Layout (`static/index.html`):**
  - **VPN Status Banner:** Polls `GET /api/status` every 5 seconds. Shows green `Proton VPN Connected (<country> · <vpn_ip>)` or red `VPN Disconnected — Downloads Paused/Blocked` when Gluetun is unhealthy or disconnected.
  - **Drop Zone:** Drag-and-drop area + file input accepting `.torrent` files (max 10 MB, validated by bencode parsing before acceptance).
  - **Category Toggle:** Two-button selector: **Movie** (default) or **Music**.
  - **Jobs List:** Shows active and recent jobs (title, category, state badge, progress %, download speed, ETA, subtitle/IMDb badge, error details if failed, and a Cancel/Delete button for active/failed jobs).
  - *My call:* Keep v1 focused on `.torrent` file uploads as requested (no magnet link parser needed initially, since `.torrent` files give immediate deterministic `info_hash` and `info.name` before submission).
- **API Endpoints:**
  - `GET /` — serves `index.html`.
  - `GET /api/status` — returns VPN connection state, VPN exit IP/country from Gluetun (`127.0.0.1:8000/v1/publicip/ip`), and active/recent jobs from SQLite.
  - `POST /api/torrents` — multipart upload (`file`: `.torrent`, `category`: `movies` | `music`). Parses `info_hash` + display name, checks for duplicate active job in SQLite, verifies VPN is healthy (rejects with `503` if VPN is down rather than queueing blind? *My call:* Reject submission with a clear UI warning if Gluetun reports disconnected so the user gets immediate feedback, or accept into `queued` only if VPN is up—rejecting with `503` on VPN down is clearer and safer), submits `.torrent` to qBittorrent with category `movies`/`music` and `ratioLimit=0`, stores job in SQLite, returns `201`.
  - `DELETE /api/torrents/{id}` — cancels active torrent in qBittorrent (`deleteFiles=true` if incomplete) or removes completed/failed history row.

### 4. Job Lifecycle & Post-Processing (`app/postprocess.py`)
A background asyncio loop ticks every 3 seconds:
1. **`downloading`:** Polls qBittorrent `GET /api/v2/torrents/info?hashes=...` for active jobs. Updates `progress`, `dlspeed`, `eta`, and `content_path` in SQLite.
2. **Completion Detection:** When `progress == 1.0` and qBittorrent state is a completed state (`pausedUP`, `uploading`, `stalledUP`, `queuedUP`, `forcedUP`, `checkingUP` -> wait until checking finishes):
   - Immediately remove the torrent from qBittorrent via `POST /api/v2/torrents/delete` with `deleteFiles=false` (enforces zero seeding).
   - Transition job to `moving`.
3. **Atomic Move:**
   - Map container `content_path` (`/downloads/complete/<category>/<name>`) to host path (`~/projects/torrent-drop/downloads/complete/<category>/<name>`).
   - Destination base:
     - `movies` -> `~/projects/jellyfin/media/Movies/<name>`
     - `music` -> `~/projects/navidrome/music/<name>`
   - *My call (collision safety):* If the destination path already exists, do **not** overwrite existing library media—mark job `failed` with a clear collision message and email the user, leaving the downloaded copy in staging for manual inspection.
   - Perform `shutil.move` (atomic `rename()` on `/dev/nvme0n1p2`).
4. **Movie Post-Processing (`fix_movies_subtitles_imdb.py`):**
   - *My call:* Add an optional `--target <path>` CLI argument (and optionally `--json-summary` or parseable structured summary) to `~/projects/jellyfin/fix_movies_subtitles_imdb.py` so the worker can process **only** the newly moved movie folder/file instead of scanning the entire `Movies` directory (avoiding unnecessary 15s NapiProjekt rate-limit delays on older missing movies). When `--target` is omitted, `fix_movies_subtitles_imdb.py` keeps its exact existing behavior.
   - Run `python3 ~/projects/jellyfin/fix_movies_subtitles_imdb.py --target <dest_path>` with a generous timeout (e.g., 5 minutes), capturing stdout + exit code.
   - **Corrupted video handling:** If `fix_movies_subtitles_imdb.py` reports the video as corrupted (e.g., `Summary.corrupted_videos` is non-empty), delete the moved payload from `~/projects/jellyfin/media/Movies`, transition the job to `failed`, and send a failure email explaining the corruption error.
   - *My call (non-corruption script failure):* If `fix_movies_subtitles_imdb.py` crashes or times out without reporting corruption (e.g., transient subtitle-provider error), keep the healthy video in `media/Movies`, transition the job to `done` with a warning flag, and include the stderr/warning in the completion email.
   - *(Optional, left to builder)* Trigger a Jellyfin library refresh if a `JELLYFIN_API_KEY` env var is provided, otherwise rely on Jellyfin's automatic library monitor/schedule.
5. **Email Notification (`app/notifier.py`):**
   - Uses `smtplib.SMTP(SMTP_HOST, SMTP_PORT)` + `starttls()` (`smtp.eu.mailgun.org:587`) with credentials from `.env` (`SMTP_USER`, `SMTP_PASSWORD`, `NOTIFY_FROM`, `NOTIFY_TO=contact@marzeta.pl`).
   - Sends on `done` (title, category, size, elapsed time, destination path, and for Movies: the `=== SUMMARY ===` block from `fix_movies_subtitles_imdb.py`) and on `failed` (stage + error reason).

### 5. Failure Handling & Recovery
- **VPN Drop Mid-Download:** Gluetun's killswitch immediately blocks all packets; qBittorrent stalls at 0 B/s without leaking the host IP. The UI banner turns red. Once Proton VPN reconnects, qBittorrent automatically resumes without user action.
- **Pi Reboot / Service Restart:** `gluetun` and `qbittorrent` use `restart: unless-stopped`; `torrent-drop.service` restarts via `systemd` and resumes polling any non-terminal jobs in `jobs.db` by their `info_hash`.
- **Duplicate Drop:** Dropping the same `.torrent` while an active job with the same `info_hash` exists returns a friendly notice instead of clobbering the active download.

## Left to the Builder
- Exact UI styling (clean dark/light responsive layout usable on laptop & phone on Wi-Fi).
- Exact bencode library choice (tiny pure-Python bencode decoder or `bencodepy` wheel).
- Optional Jellyfin/Navidrome API refresh call if API credentials are configured in `.env`.
- `systemd` unit file specifics (`Restart=always`, `After=docker.service`).
