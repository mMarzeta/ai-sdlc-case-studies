# Magnet Links Support for `torrent-drop` — Design Specification

**Date:** 2026-11-14  
**Status:** Draft (pending builder check & user approval)  
**Scope:** Add `magnet:?...` URI support to `torrent-drop` alongside existing `.torrent` file uploads.

---

## 1. Overview & Goals

Extend `torrent-drop` so users can paste `magnet:?...` links directly in the Web UI (using the existing Movies / Music library selector) and have them validated, deduplicated, downloaded behind Proton VPN via qBittorrent, monitored for metadata resolution, post-processed, and notified via email identically to `.torrent` uploads.

### Goals
- Accept `magnet:?...` links via a text input + submit button below the dropzone in `app/static/index.html`.
- Normalize BitTorrent v1 info-hashes (both 40-char hex and 32-char Base32) to 40-char lowercase hex so duplicate detection (`ACTIVE_STATES`) and qBittorrent polling work seamlessly across `.torrent` files and magnet links.
- Sync real torrent `name` and `total_size` from qBittorrent into SQLite once DHT/peer metadata resolution completes.
- Automatically fail dead magnets stuck without metadata after a configurable timeout (default: 15 minutes / `900s`), clean them up from qBittorrent, and send a failure notification email.
- Preserve existing `.torrent` upload behavior and SQLite schema with zero schema migrations.

### Non-Goals (Out of Scope)
- Standalone BitTorrent v2-only magnets (`urn:btmh:...` without a companion `urn:btih:...` hash) — rejected with `400`. (Hybrid v1+v2 magnets that include `urn:btih:...` are supported.)
- Batch/multi-line magnet submission or `.magnet` file uploads.
- Altering SQLite `jobs` table columns or introducing new job state strings.

---

## 2. Architecture (Approach A)

```
UI (#magnetForm)
   │ POST /api/magnets {"magnet": "...", "category": "movies"|"music"}
   ▼
FastAPI (app/main.py)
   ├─ parse_magnet_uri()  ──► 400 / 413 on invalid or oversized URI
   ├─ _enqueue_torrent_job()
   │     ├─ VPN check     ──► 503 if VPN disconnected
   │     ├─ qB config     ──► 503 if qBittorrent unreachable
   │     ├─ store.create_job(..., total_size=0) ──► 409 if info_hash active
   │     └─ qb.add_magnet(uri, category)        ──► 500 + mark failed on error
   ▼
Worker Loop (app/worker.py)
   ├─ While unresolved (metaDL / total_size == 0):
   │     ├─ If elapsed >= MAGNET_METADATA_TIMEOUT_SEC (900s):
   │     │     qb.delete_torrent(hash, delete_files=True)
   │     │     store.update_job(state="failed", error=...)
   │     │     send failure email
   │     └─ Else: update progress/speed/eta/content_path
   └─ Once metadata arrives (prog.size > 0 & not metaDL):
         sync name & total_size into DB, then continue normal download & post-process
```

---

## 3. Component Design

### 3.1 Magnet URI Parser (`app/bencode.py`)

Add `parse_magnet_uri(uri: str) -> TorrentMeta` to `app/bencode.py`, reusing `TorrentParseError` and `TorrentMeta(info_hash, name, total_size)`.

- **Size limit:** Strip leading/trailing whitespace. Empty string raises `TorrentParseError("Empty magnet link")`. URIs longer than `16384` characters raise a dedicated `MagnetTooLargeError(TorrentParseError)` (or checked in endpoint for HTTP `413`; let's define `MAX_MAGNET_LENGTH = 16384` and raise `TorrentParseError` with HTTP `413` or `400` — specifically `413` in endpoint if `len(raw) > MAX_MAGNET_LENGTH`, keeping parser pure).
- **Scheme validation:** Require scheme `magnet:` (case-insensitive) and query string (`magnet:?...`) via `urllib.parse.urlsplit`.
- **Info-hash extraction (`xt`):**
  - Parse query parameters using `urllib.parse.parse_qs(parsed.query, keep_blank_values=False)`.
  - Iterate through all `xt` values (supports hybrid magnets with multiple `xt` parameters).
  - Match `urn:btih:<token>` case-insensitively:
    - **40 hex characters** (`^[0-9a-fA-F]{40}$`): normalize to `token.lower()`.
    - **32 Base32 characters** (`^[A-Za-z2-7]{32}$`): decode via `base64.b32decode(token.upper(), casefold=False)` -> verify length is 20 bytes -> `.hex().lower()`.
  - Use the first valid `urn:btih:` value found.
  - If no valid `urn:btih:` is found:
    - If `urn:btmh:` is present, raise `TorrentParseError("BitTorrent v2-only magnet links (urn:btmh) without a v1 btih hash are not supported")`.
    - Otherwise raise `TorrentParseError("Magnet link is missing a valid urn:btih info hash")`.
- **Display name (`dn`):**
  - Take the first non-empty `dn` value after `.strip()` (already percent-decoded by `parse_qs`), truncated to `255` characters.
  - If missing or blank, fallback to `f"magnet-{info_hash[:12]}"`.
- **Returned object:** `TorrentMeta(info_hash=info_hash, name=name, total_size=0)`.

### 3.2 Configuration (`app/config.py`)

Extend `Settings` and `load_settings()`:
- Field: `magnet_metadata_timeout_sec: int = 900`
- Env / `.env` key: `MAGNET_METADATA_TIMEOUT_SEC` (default `"900"`).
- Parsing: parse as `int`; on `ValueError`, fall back to `900`. A value `<= 0` disables automatic metadata timeout.

### 3.3 qBittorrent Client (`app/torrent_client.py`)

1. **`TorrentProgress` dataclass:**
   - Add `name: str = ""` (with default `""` so all existing callers/tests remain compatible).
2. **`get_torrents(hashes)`:**
   - Populate `name=str(item.get("name", ""))`.
   - Normalize `size`: `raw_size = item.get("size", item.get("total_size", 0))`; convert to `max(0, int(raw_size or 0))` so placeholder `-1` values from qBittorrent prior to metadata resolution never become negative sizes.
3. **`add_magnet(self, magnet_uri: str, category: str) -> None`:**
   - `POST /api/v2/torrents/add` with `data={"urls": magnet_uri, "category": category, "ratioLimit": "0.0"}`.
   - Check `res.text.strip() == "Fails."` and raise `QBittorrentError("Failed to add magnet: qBittorrent returned 'Fails.'")`.

### 3.4 FastAPI Endpoint & Shared Enqueue Flow (`app/main.py`)

1. **Request model:**
   ```python
   class MagnetRequest(BaseModel):
       magnet: str
       category: str
   ```
2. **Endpoint `POST /api/magnets` (`status_code=201`):**
   - Validate `category.strip().lower() in ("movies", "music")`, else `400`.
   - Check `len(payload.magnet.strip()) > MAX_MAGNET_LENGTH` -> `413 Payload Too Large`.
   - Parse via `parse_magnet_uri(payload.magnet)` -> `400 Bad Request` on `TorrentParseError`.
   - Delegate to shared helper `_enqueue_torrent_job(...)` and return `dataclasses.asdict(job)`.
3. **Shared helper `_enqueue_torrent_job(...)`:**
   Used by both `POST /api/torrents` and `POST /api/magnets` to avoid duplicating submission logic:
   1. Check `vpn = await app.state.vpn_checker()`; if not `vpn.connected`, raise `503`.
   2. If not `app.state.qb_configured`, call `await qb.ensure_configured("/downloads", cfg.qb_interface)`; on failure raise `503`.
   3. Call `store.create_job(info_hash=meta.info_hash, name=meta.name, category=cat, total_size=meta.total_size)`; catch `DuplicateActiveJobError` -> raise `409`.
   4. Await client submission callback (`qb.add_torrent(...)` or `qb.add_magnet(...)`); on exception call `store.update_job(job.id, state="failed", error=f"qBittorrent submission error: {exc}")` and raise `500`.
4. **Cancellation (`DELETE /api/torrents/{job_id}`):**
   - Existing endpoint requires no backend changes; deleting a magnet job during `submitted` or `downloading` (including `metaDL`) removes it from qBittorrent (`delete_files=True`) and deletes the DB row.

### 3.5 Worker Metadata Sync & Timeout (`app/worker.py`)

Define `METADATA_QB_STATES = {"metaDL", "forcedMetaDL"}` in `app/worker.py`.

In `_process_job(job, torrents_dict, store, qb, cfg)` when `job.state in ("submitted", "downloading")`:

1. **Check for unresolved metadata:**
   A job is still waiting for metadata when:
   `is_waiting_metadata = (prog.state in METADATA_QB_STATES) or (job.total_size == 0 and prog.size <= 0 and prog.progress < 1.0)`

   - If `is_waiting_metadata` and `cfg.magnet_metadata_timeout_sec > 0`:
     - Parse `job.created_at` with `datetime.fromisoformat(...)` (assume UTC if naive).
     - Compute `elapsed = (datetime.now(timezone.utc) - created_dt).total_seconds()`.
     - If `elapsed >= cfg.magnet_metadata_timeout_sec`:
       - Best-effort `await qb.delete_torrent(job.info_hash, delete_files=True)` (catch & log warning if qBittorrent fails).
       - Update job: `job = store.update_job(job.id, state="failed", dlspeed=0, eta=0, error=f"Timed out waiting for magnet metadata after {cfg.magnet_metadata_timeout_sec}s (no peers/DHT response).")`.
       - Send failure email: `subject, body = format_failure_email(job)` via `await asyncio.to_thread(send_email, cfg, subject, body)` (catch & log exception).
       - Return early.

2. **Sync resolved metadata (`name` & `total_size`):**
   When metadata has arrived (`not is_waiting_metadata` and `prog.size > 0`):
   - Prepare metadata updates when `job.total_size == 0`:
     - `total_size = prog.size`
     - `name = prog.name.strip()[:255]` if `prog.name and prog.name.strip()` else keep `job.name`.
   - Persist `total_size` and `name` into `store.update_job(...)`:
     - **Important edge case (fast single-poll completion):** If `prog.progress >= 1.0 and prog.state in COMPLETED_QB_STATES`, apply the `name`/`total_size` update to `store` FIRST so the `JobRecord` passed to `_handle_completion(...)` already carries the real torrent `name` and `total_size` for destination routing and `format_completion_email`.
     - Otherwise, include `name` and `total_size` in the regular `state="downloading"` `store.update_job(...)` call.

> **Note:** Regular `.torrent` uploads always enter the DB with `total_size > 0` (parsed from bencode) and do not enter `metaDL`, so neither the metadata timeout nor the `name` overwrite runs for `.torrent` jobs.

### 3.6 Web UI (`app/static/index.html`)

1. **Magnet Input Form (below `#dropzone` inside the first `.card`):**
   - Subtle divider label (`or paste magnet link`).
   - `<form id="magnetForm" class="magnet-form">` containing:
     - `<input type="text" id="magnetInput" placeholder="magnet:?xt=urn:btih:..." autocomplete="off" spellcheck="false">`
     - `<button type="submit" id="magnetSubmitBtn">Add Magnet</button>`
   - Styled to match the existing dark slate theme (`--bg`, `--card-border`, `--accent`).
   - Submission handler (`handleMagnetSubmit`):
     - Prevents default form submit; ignores while `isUploading` is true.
     - Trims input; verifies non-empty and `^magnet:\?` prefix client-side for immediate feedback before sending `POST /api/magnets` with `{ magnet, category }`.
     - Disables `#magnetInput` and `#magnetSubmitBtn` during flight.
     - On `201`: clears `#magnetInput`, shows success alert `Successfully queued: <name>`, calls `fetchStatus()`.
     - On error: shows error alert with `data.detail`.
   - Update dropzone subtitle/empty state copy slightly to mention `.torrent` files or `magnet:?` links.

2. **Job Status Display (`updateJobs`):**
   - When `job.state === "submitted"` or (`job.state === "downloading"` and `job.total_size === 0` and `job.progress === 0`):
     render `statusText = "Fetching metadata from DHT/peers..."` instead of `"0.0% · 0 B/s · ETA: 0s"`.

---

## 4. Verification Plan

1. **Unit tests (`tests/test_bencode.py`):**
   - `parse_magnet_uri` with 40-char hex (mixed case), 32-char Base32 (uppercase & lowercase), missing `dn`, URL-encoded `dn`, long `dn` truncation, hybrid `btih` + `btmh` magnet, v2-only `btmh` magnet (rejected), malformed/empty/missing `xt`/invalid Base32.
2. **Client tests (`tests/test_clients.py`):**
   - `add_magnet` sends `urls`, `category`, `ratioLimit="0.0"` to `/api/v2/torrents/add` and raises `QBittorrentError` on `Fails.`.
   - `get_torrents` populates `TorrentProgress.name` and clamps negative `size` to `0`.
3. **API tests (`tests/test_api.py`):**
   - `POST /api/magnets` returns `201` and creates job with normalized lowercase hex `info_hash` and `total_size=0`.
   - Rejects invalid category (`400`), invalid magnet (`400`), oversized magnet (`413`), duplicate active `info_hash` across `.torrent` and magnet (`409`), VPN down (`503`), qBittorrent unreachable (`503`), and qBittorrent submission failure (`500` + DB job marked `failed`).
4. **Worker tests (`tests/test_postprocess_worker.py`):**
   - Metadata resolution updates `name` and `total_size` during active download.
   - Fast magnet resolving and completing within one poll updates `name` and `total_size` before completion email/post-process.
   - Dead magnet stuck in `metaDL` (or `stalledDL` with `size == 0`) beyond `magnet_metadata_timeout_sec` deletes from qBittorrent, marks job `failed`, and sends failure email.
   - Active `.torrent` job (`total_size > 0`) or magnet below timeout is not failed.
5. **Regression & Live Verification:**
   - Run full `pytest` suite (`tests/`).
   - Restart `torrent-drop.service` and test live UI + endpoint against `gluetun` + `qbittorrent`.
