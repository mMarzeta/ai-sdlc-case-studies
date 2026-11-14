# Magnet Links Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `magnet:?...` URI submission, normalized `btih` info-hash parsing, qBittorrent `urls` submission, worker metadata sync (`name` and `total_size`), automatic 15-minute `metaDL` timeout with failure email, and a magnet text input in the Web UI.

**Architecture:** Extend `app/bencode.py` with `parse_magnet_uri()` returning `TorrentMeta(..., total_size=0)`, add `add_magnet()` and `TorrentProgress.name` to `app/torrent_client.py`, add `POST /api/magnets` in `app/main.py` sharing a single `_enqueue_torrent_job()` helper with `POST /api/torrents`, sync resolved metadata and enforce `MAGNET_METADATA_TIMEOUT_SEC` (default `900`s) in `app/worker.py`, and add a magnet form below `#dropzone` in `app/static/index.html`. No SQLite schema changes required.

**Tech Stack:** Python 3, FastAPI, Pydantic, httpx, SQLite (`JobStore`), pytest, Vanilla HTML/CSS/JS.

**Spec:** `~/projects/docs/superpowers/specs/2026-11-14-magnet-links-design.md`

**Global Constraints:**
- Run pytest via `~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests` after every task.
- Keep `TorrentMeta`, `parse_torrent_bytes`, `POST /api/torrents`, and `.torrent` jobs completely backward compatible.
- Do not add SQLite schema migrations.
- Maintain existing comments/docstrings unrelated to changed blocks.

---

### Task 1: Magnet URI Parser (`app/bencode.py`)

**Files:**
- Modify: `torrent-drop/app/bencode.py`
- Modify: `torrent-drop/tests/test_bencode.py`

- [ ] **Step 1: Write failing tests for `parse_magnet_uri`**

Append to `torrent-drop/tests/test_bencode.py`:

```python
from bencode import MAX_MAGNET_LENGTH, MagnetTooLargeError, parse_magnet_uri


def test_parse_magnet_hex_with_dn():
    h = "A1B2C3D4E5F60718293A4B5C6D7E8F9012345678"
    uri = f"magnet:?xt=urn:btih:{h}&dn=My%20Movie%20%282024%29&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337"
    meta = parse_magnet_uri(uri)
    assert meta.info_hash == h.lower()
    assert meta.name == "My Movie (2024)"
    assert meta.total_size == 0


def test_parse_magnet_base32_and_missing_dn():
    # 20 bytes 0x00..0x13 in base32 (32 chars)
    import base64
    raw_bytes = bytes(range(20))
    b32 = base64.b32encode(raw_bytes).decode("ascii").lower()
    meta = parse_magnet_uri(f"  MAGNET:?xt=urn:btih:{b32}&dn=   ")
    assert meta.info_hash == raw_bytes.hex()
    assert meta.name == f"magnet-{raw_bytes.hex()[:12]}"
    assert meta.total_size == 0


def test_parse_magnet_hybrid_v1_v2_uses_btih_and_truncates_dn():
    h = "0123456789abcdef0123456789abcdef01234567"
    v2 = "1220" + ("ab" * 32)
    long_name = "x" * 300
    uri = f"magnet:?xt=urn:btmh:{v2}&xt=urn:btih:{h}&dn={long_name}"
    meta = parse_magnet_uri(uri)
    assert meta.info_hash == h
    assert meta.name == "x" * 255


def test_parse_magnet_v2_only_rejected():
    v2 = "1220" + ("ab" * 32)
    with pytest.raises(TorrentParseError, match="btmh"):
        parse_magnet_uri(f"magnet:?xt=urn:btmh:{v2}&dn=Test")


@pytest.mark.parametrize(
    "bad_uri",
    [
        "",
        "   ",
        "http://example.com/?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
        "magnet:",
        "magnet:?",
        "magnet:?dn=OnlyName",
        "magnet:?xt=urn:btih:short",
        "magnet:?xt=urn:btih:" + ("z" * 40),
        "magnet:?xt=urn:btih:" + ("1" * 32),  # '1' is invalid base32
    ],
)
def test_parse_magnet_invalid_raises(bad_uri: str):
    with pytest.raises(TorrentParseError):
        parse_magnet_uri(bad_uri)


def test_parse_magnet_too_large_raises():
    h = "0123456789abcdef0123456789abcdef01234567"
    oversized = f"magnet:?xt=urn:btih:{h}&dn=" + ("a" * (MAX_MAGNET_LENGTH + 10))
    with pytest.raises(MagnetTooLargeError):
        parse_magnet_uri(oversized)
```

- [ ] **Step 2: Run test to verify failure**

Run:
`~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_bencode.py`
Expected: `ImportError` (`MAX_MAGNET_LENGTH`, `MagnetTooLargeError`, `parse_magnet_uri` missing).

- [ ] **Step 3: Implement `parse_magnet_uri` in `torrent-drop/app/bencode.py`**

Add imports (`base64`, `re`, `urllib.parse`), constants, `MagnetTooLargeError`, and `parse_magnet_uri(uri: str) -> TorrentMeta`:

```python
MAX_MAGNET_LENGTH = 16384
_HEX_40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_B32_32_RE = re.compile(r"^[A-Za-z2-7]{32}$")


class MagnetTooLargeError(TorrentParseError):
    """Raised when a magnet URI exceeds MAX_MAGNET_LENGTH."""


def parse_magnet_uri(uri: str) -> TorrentMeta:
    """Parse and validate a magnet:? URI, normalizing btih to 40-char lowercase hex."""
    if not isinstance(uri, str):
        raise TorrentParseError("Magnet link must be a string")
    cleaned = uri.strip()
    if not cleaned:
        raise TorrentParseError("Empty magnet link")
    if len(cleaned) > MAX_MAGNET_LENGTH:
        raise MagnetTooLargeError(
            f"Magnet link exceeds maximum length ({len(cleaned)} > {MAX_MAGNET_LENGTH} chars)"
        )

    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme.lower() != "magnet" or not parsed.query:
        raise TorrentParseError("Invalid magnet URI format (expected magnet:?...)")

    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
    xt_values = params.get("xt", [])

    info_hash: str | None = None
    saw_btmh = False
    for xt in xt_values:
        xt_clean = xt.strip()
        lower_xt = xt_clean.lower()
        if lower_xt.startswith("urn:btih:"):
            token = xt_clean[9:]
            if _HEX_40_RE.match(token):
                info_hash = token.lower()
                break
            if _B32_32_RE.match(token):
                try:
                    raw = base64.b32decode(token.upper(), casefold=False)
                except Exception as exc:
                    raise TorrentParseError(f"Invalid Base32 btih hash: {exc}") from exc
                if len(raw) == 20:
                    info_hash = raw.hex().lower()
                    break
        elif lower_xt.startswith("urn:btmh:"):
            saw_btmh = True

    if not info_hash:
        if saw_btmh:
            raise TorrentParseError(
                "BitTorrent v2-only magnet links (urn:btmh) without a v1 btih hash are not supported"
            )
        raise TorrentParseError("Magnet link is missing a valid urn:btih info hash")

    dn_values = params.get("dn", [])
    display_name = ""
    for dn in dn_values:
        cand = dn.strip()
        if cand:
            display_name = cand[:255]
            break
    if not display_name:
        display_name = f"magnet-{info_hash[:12]}"

    return TorrentMeta(info_hash=info_hash, name=display_name, total_size=0)
```

- [ ] **Step 4: Run `test_bencode.py` to verify pass**

Run:
`~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_bencode.py`
Expected: All passed.

---

### Task 2: Config Timeout Setting & qBittorrent Magnet Client (`app/config.py`, `app/torrent_client.py`)

**Files:**
- Modify: `torrent-drop/app/config.py`
- Modify: `torrent-drop/app/torrent_client.py`
- Modify: `torrent-drop/tests/test_clients.py`

- [ ] **Step 1: Write failing tests in `torrent-drop/tests/test_clients.py`**

Read the end of `torrent-drop/tests/test_clients.py` to place new tests cleanly, then add tests for:
- `QBittorrentClient.add_magnet` sending `POST /api/v2/torrents/add` with `urls`, `category`, `ratioLimit="0.0"`, and raising `QBittorrentError` on `Fails.`.
- `QBittorrentClient.get_torrents` extracting `name` into `TorrentProgress.name` and clamping negative `size` (e.g., `-1`) to `0`.
- `load_settings()` reading `MAGNET_METADATA_TIMEOUT_SEC` (default `900`, custom integer, fallback `900` on invalid value, `0` allowed to disable).

- [ ] **Step 2: Run `test_clients.py` to verify failure**

Run:
`~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_clients.py`
Expected: Failure on `add_magnet` / `TorrentProgress.name` / `magnet_metadata_timeout_sec`.

- [ ] **Step 3: Implement changes in `app/config.py` and `app/torrent_client.py`**

In `app/config.py`:
- Add `magnet_metadata_timeout_sec: int = 900` to `Settings`.
- In `load_settings()`: parse `MAGNET_METADATA_TIMEOUT_SEC` (default `"900"`, fallback `900` on `ValueError`) and pass to `Settings(...)`.

In `app/torrent_client.py`:
- Add `name: str = ""` to `TorrentProgress`.
- Add `add_magnet(self, magnet_uri: str, category: str) -> None`:
  ```python
  async def add_magnet(self, magnet_uri: str, category: str) -> None:
      data = {
          "urls": magnet_uri,
          "category": category,
          "ratioLimit": "0.0",
      }
      res = await self._request(
          "POST",
          "/api/v2/torrents/add",
          data=data,
      )
      if res.text.strip() == "Fails.":
          raise QBittorrentError("Failed to add magnet: qBittorrent returned 'Fails.'")
  ```
- In `get_torrents()`:
  ```python
  raw_size = item.get("size", item.get("total_size", 0))
  prog = TorrentProgress(
      info_hash=h,
      state=str(item.get("state", "")),
      progress=float(item.get("progress", 0.0)),
      dlspeed=int(item.get("dlspeed", 0)),
      eta=int(item.get("eta", 0)),
      content_path=str(item.get("content_path", "")),
      size=max(0, int(raw_size or 0)),
      name=str(item.get("name", "")),
  )
  ```

- [ ] **Step 4: Run `test_clients.py` to verify pass**

Run:
`~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_clients.py`
Expected: All passed.

---

### Task 3: `POST /api/magnets` Endpoint & Shared Enqueue Flow (`app/main.py`)

**Files:**
- Modify: `torrent-drop/app/main.py`
- Modify: `torrent-drop/tests/test_api.py`

- [ ] **Step 1: Write failing API tests in `torrent-drop/tests/test_api.py`**

Update `mock_qb` fixture to include `qb.add_magnet = AsyncMock(return_value=None)`. Add tests covering:
- `POST /api/magnets` returns `201`, creates job in `JobStore` with lowercase 40-char hex `info_hash`, `total_size == 0`, calls `mock_qb.add_magnet(magnet, cat)`.
- Base32 magnet link creates same normalized hex `info_hash` and detects `409` duplicate when an active `.torrent` or magnet job with that hash already exists.
- Invalid category (`400`), malformed magnet (`400`), v2-only `btmh` magnet (`400`), oversized magnet > `MAX_MAGNET_LENGTH` (`413`).
- VPN disconnected (`503`), qBittorrent `ensure_configured` failure (`503`), and `qb.add_magnet` error (`500` + DB job state marked `"failed"`).

- [ ] **Step 2: Run `test_api.py` to verify failure**

Run:
`~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_api.py`
Expected: `404` / assertion failures on `/api/magnets`.

- [ ] **Step 3: Refactor `_enqueue_torrent_job` and add `POST /api/magnets` in `app/main.py`**

- Import `MAX_MAGNET_LENGTH`, `MagnetTooLargeError`, `TorrentMeta`, `parse_magnet_uri` from `bencode`, and `BaseModel` from `pydantic`.
- Define `class MagnetRequest(BaseModel): magnet: str; category: str`.
- Extract shared async helper inside `create_app`:
  ```python
  async def _enqueue_job(
      meta: TorrentMeta,
      cat: str,
      submit_fn: Callable[[], Awaitable[None]],
  ) -> JobRecord:
      vpn = await app.state.vpn_checker()
      if not vpn.connected:
          raise HTTPException(
              status_code=503,
              detail=f"VPN is not connected ({vpn.status_text}). Downloads blocked.",
          )

      if not getattr(app.state, "qb_configured", False):
          try:
              await qb.ensure_configured("/downloads", cfg.qb_interface)
              app.state.qb_configured = True
          except Exception as exc:
              logger.warning("qBittorrent is unreachable during submission: %s", exc)
              raise HTTPException(
                  status_code=503,
                  detail=f"qBittorrent client is unreachable or not ready: {exc}",
              )

      try:
          job = store.create_job(
              info_hash=meta.info_hash,
              name=meta.name,
              category=cat,
              total_size=meta.total_size,
          )
      except DuplicateActiveJobError as exc:
          raise HTTPException(status_code=409, detail=str(exc))

      try:
          await submit_fn()
      except Exception as exc:
          store.update_job(job.id, state="failed", error=f"qBittorrent submission error: {exc}")
          raise HTTPException(status_code=500, detail=f"Failed to submit torrent to client: {exc}")

      return job
  ```
- Update `POST /api/torrents` to call `_enqueue_job(meta, cat, lambda: qb.add_torrent(content, filename, cat))`.
- Add `POST /api/magnets`:
  ```python
  @app.post("/api/magnets", status_code=201)
  async def submit_magnet(payload: MagnetRequest):
      cat = payload.category.strip().lower()
      if cat not in ("movies", "music"):
          raise HTTPException(
              status_code=400,
              detail=f"Invalid category '{payload.category}'. Must be 'movies' or 'music'.",
          )

      magnet_uri = payload.magnet.strip()
      if len(magnet_uri) > MAX_MAGNET_LENGTH:
          raise HTTPException(
              status_code=413,
              detail=f"Magnet URI too large ({len(magnet_uri)} chars). Maximum length is {MAX_MAGNET_LENGTH}.",
          )

      try:
          meta = parse_magnet_uri(magnet_uri)
      except MagnetTooLargeError as exc:
          raise HTTPException(status_code=413, detail=str(exc))
      except TorrentParseError as exc:
          raise HTTPException(status_code=400, detail=f"Invalid magnet link: {exc}")

      job = await _enqueue_job(meta, cat, lambda: qb.add_magnet(magnet_uri, cat))
      return dataclasses.asdict(job)
  ```

- [ ] **Step 4: Run `test_api.py` to verify pass**

Run:
`~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_api.py`
Expected: All passed.

---

### Task 4: Worker Metadata Sync & Automatic Timeout (`app/worker.py`)

**Files:**
- Modify: `torrent-drop/app/worker.py`
- Modify: `torrent-drop/tests/test_postprocess_worker.py`

- [ ] **Step 1: Write failing worker tests in `torrent-drop/tests/test_postprocess_worker.py`**

Add tests for:
1. **Metadata sync while downloading:** Job starts with `total_size=0`, `name="magnet-0123456789ab"`; qBittorrent returns `TorrentProgress(state="downloading", progress=0.25, size=1500000, name="Inception (2010)", ...)`. `poll_once()` updates `name` and `total_size` in DB.
2. **Fast single-poll completion after metadata resolves:** Job starts with `total_size=0`, `name="magnet-..."`; qBittorrent returns `progress=1.0`, `state="pausedUP"`, `size=5000`, `name="Real Movie Name"`. Completion moves files AND `format_completion_email` receives the updated `name` and `total_size`.
3. **Metadata resolution timeout:** Job created > `cfg.magnet_metadata_timeout_sec` ago (backdate `created_at` in SQLite or set `magnet_metadata_timeout_sec=10`), qBittorrent reports `state="metaDL"`, `size=0`, `progress=0.0`. `poll_once()` calls `qb.delete_torrent(hash, delete_files=True)`, marks job `"failed"` with timeout message, and calls `send_email` once with failure email.
4. **No false-positive timeout:**
   - Magnet in `metaDL` below timeout stays `"downloading"`.
   - Regular `.torrent` job (`total_size > 0`) in `stalledDL` older than timeout is NOT timed out as metadata failure.
   - `magnet_metadata_timeout_sec <= 0` disables timeout.

- [ ] **Step 2: Run `test_postprocess_worker.py` to verify failure**

Run:
`~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_postprocess_worker.py`
Expected: Failure on metadata sync & timeout assertions.

- [ ] **Step 3: Implement metadata sync & timeout in `app/worker.py`**

Add helper and update `_process_job`:

```python
METADATA_QB_STATES = {"metaDL", "forcedMetaDL"}


def _is_metadata_timed_out(job: JobRecord, timeout_sec: int) -> bool:
    if timeout_sec <= 0 or not job.created_at:
        return False
    try:
        created = datetime.fromisoformat(job.created_at)
    except ValueError:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - created).total_seconds()
    return elapsed >= timeout_sec
```

In `_process_job`:
```python
    if job.state in ("submitted", "downloading"):
        prog = torrents_dict.get(job.info_hash.lower()) or torrents_dict.get(job.info_hash)
        if not prog:
            return

        waiting_metadata = (
            prog.state in METADATA_QB_STATES
            or (job.total_size == 0 and prog.size <= 0 and prog.progress < 1.0)
        )
        if waiting_metadata and _is_metadata_timed_out(job, cfg.magnet_metadata_timeout_sec):
            try:
                await qb.delete_torrent(job.info_hash, delete_files=True)
            except Exception as del_err:
                logger.warning(
                    "Failed to delete timed-out magnet %s from qBittorrent: %s",
                    job.info_hash,
                    del_err,
                )
            failed_job = store.update_job(
                job.id,
                state="failed",
                dlspeed=0,
                eta=0,
                error=(
                    f"Timed out waiting for magnet metadata after "
                    f"{cfg.magnet_metadata_timeout_sec}s (no peers/DHT response)"
                ),
            )
            try:
                subject, body = format_failure_email(failed_job)
                await asyncio.to_thread(send_email, cfg, subject, body)
            except Exception as email_err:
                logger.exception(
                    "Failed to send metadata timeout email for job %d: %s",
                    job.id,
                    email_err,
                )
            return

        meta_updates: dict[str, Any] = {}
        if not waiting_metadata and job.total_size == 0 and prog.size > 0:
            meta_updates["total_size"] = prog.size
            if prog.name and prog.name.strip():
                meta_updates["name"] = prog.name.strip()[:255]

        if prog.progress >= 1.0 and prog.state in COMPLETED_QB_STATES:
            if meta_updates:
                job = store.update_job(job.id, **meta_updates)
            await _handle_completion(job, prog.content_path or job.content_path, store, qb, cfg)
        else:
            content_path = prog.content_path or job.content_path
            store.update_job(
                job.id,
                state="downloading",
                progress=prog.progress,
                dlspeed=prog.dlspeed,
                eta=prog.eta,
                content_path=content_path,
                **meta_updates,
            )
```

- [ ] **Step 4: Run `test_postprocess_worker.py` to verify pass**

Run:
`~/projects/torrent-drop/app/.venv/bin/pytest ~/projects/torrent-drop/tests/test_postprocess_worker.py`
Expected: All passed.

---

### Task 5: Web UI Magnet Input & Status Display (`app/static/index.html`) + Full Verification

**Files:**
- Modify: `torrent-drop/app/static/index.html`

- [ ] **Step 1: Add magnet input CSS & form markup in `app/static/index.html`**

- Add CSS styles (`.or-divider`, `.magnet-form`, `#magnetInput`, `#magnetSubmitBtn`, responsive wrap on narrow screens) matching `--bg`, `--card-border`, `--accent`, `--accent-hover`, `--text`.
- Inside the upload `.card` directly below `#dropzone`:
  ```html
  <div class="or-divider"><span>or paste magnet link</span></div>

  <form id="magnetForm" class="magnet-form">
    <input
      type="text"
      id="magnetInput"
      placeholder="magnet:?xt=urn:btih:..."
      autocomplete="off"
      spellcheck="false"
    >
    <button type="submit" id="magnetSubmitBtn">Add Magnet</button>
  </form>
  ```
- Update `.dropzone-desc` and `.empty-state` wording to note `.torrent` files or `magnet:?` links.

- [ ] **Step 2: Add JS submit handler & metadata status formatting in `app/static/index.html`**

- Wire `magnetForm.addEventListener("submit", handleMagnetSubmit)`:
  - Guard with `if (isUploading) return;`.
  - Trim `#magnetInput.value`; validate non-empty and `/^magnet:\?/i.test(magnet)` (show error alert if invalid).
  - Read selected `category`, disable `#magnetInput` and `#magnetSubmitBtn`, `POST /api/magnets` JSON.
  - On `resp.ok`: clear `#magnetInput`, show `Successfully queued: ${data.name || "magnet"}` success alert, call `fetchStatus()`.
  - On error: show error alert with `data.detail`.
- In `updateJobs(jobs)`:
  - When `job.state === "submitted"` or (`job.state === "downloading"` && `job.total_size === 0` && `job.progress === 0`), set `statusText = "Fetching metadata from DHT/peers..."`.

- [ ] **Step 3: Run full test suite**

Run:
`~/projects/torrent-drop/app/.venv/bin/pytest -v ~/projects/torrent-drop/tests`
Expected: All tests pass with 0 failures / 0 skipped.

- [ ] **Step 4: Restart `torrent-drop.service` and smoke-test live endpoint**

- `sudo systemctl restart torrent-drop.service && systemctl status torrent-drop.service --no-pager`
- Verify `curl -s http://127.0.0.1:8088/api/status` returns `200`, `POST /api/magnets` rejects malformed magnet with `400` and oversized with `413`, and static HTML includes `#magnetForm`.
