# Rich Polish HTML Emails with Movie Posters — Design Specification

**Date:** 2026-11-14  
**Status:** Draft (pending builder check)  
**Scope:** Upgrade `torrent-drop` notification emails to Polish rich HTML (`multipart/alternative` + `multipart/related` inline CID posters) with IMDb metadata, clean `text/plain` fallbacks, and direct links to Jellyfin (`https://jellyfin.marzeta.pl/`) and IMDb.

---

## 1. Goals

- Enrich `fix_movies_subtitles_imdb.py` `JSON_SUMMARY` with resolved IMDb metadata (`imdb_id`, `title`, `year`, `actors`, `poster_url`) without issuing extra IMDb requests.
- Attach a movie poster inline (`cid:poster`) when available from local artwork (`folder.jpg`/`poster.jpg`) or IMDb `poster_url`, scaled to `500px` width and never blocking email delivery if image download fails.
- Render responsive, dark-themed Polish HTML email cards for Movies (with poster, cast, subtitle/IMDb status pills, Jellyfin & IMDb CTA buttons), Music, and Failures/Timeouts, while keeping full Polish `text/plain` fallbacks.
- Set `Settings.jellyfin_url` default to `https://jellyfin.marzeta.pl` (configurable via `JELLYFIN_URL` in `.env` / `.env.example`).

---

## 2. Component Design

### 2.1 IMDb Metadata Export (`jellyfin/fix_movies_subtitles_imdb.py`)

- Add `movie_meta: Optional[dict[str, Any]] = None` to `Summary`.
- Add helper `_record_movie_meta(summary: Summary, title: str, year: Optional[int], info: Optional[dict], fallback_imdb: Optional[str] = None) -> None`:
  - Only populates `summary.movie_meta` if `None` (first processed movie wins for `--target`).
  - Fields:
    - `imdb_id`: `(info or {}).get("id") or fallback_imdb` (only if matching `^tt\d{6,10}$`, else `None`)
    - `title`: `(info or {}).get("l") or title`
    - `year`: `(info or {}).get("y") or year`
    - `actors`: `(info or {}).get("s") or ""`
    - `poster_url`: `((info or {}).get("i") or {}).get("imageUrl") or ""`
- Call `_record_movie_meta` in `fix_imdb_in_nfo(...)`:
  - When existing IMDb ID is already valid (`summary.imdb_ok += 1`): pass `info` from `imdb_lookup_id(existing_imdb)`.
  - When IMDb ID is resolved/fixed via `imdb_search_movie`: pass `hit`.
  - When `imdb_search_movie` returns `None`: pass `None` and `fallback_imdb=existing_imdb`.

### 2.2 Configuration (`torrent-drop/app/config.py`, `.env.example`, `.env`)

- Change `Settings.jellyfin_url` default from `None` to `"https://jellyfin.marzeta.pl"`.
- In `load_settings()`, treat unset `JELLYFIN_URL` as `"https://jellyfin.marzeta.pl"` (and explicit empty string `JELLYFIN_URL=""` as `None` to allow disabling the link).
- Update `torrent-drop/.env.example` and live `.env` with `JELLYFIN_URL=https://jellyfin.marzeta.pl`.

### 2.3 Email Formatting & Inline Poster Fetching (`torrent-drop/app/notifier.py`)

1. **`resolve_poster_image(job: JobRecord, subtitle_summary: dict[str, Any] | None = None) -> tuple[bytes, str] | None`:**
   - Maximum poster size: `2 * 1024 * 1024` bytes (2 MB).
   - **Local check:** If `job.dest_path` exists as a directory, check `folder.jpg`, `poster.jpg`, `folder.png`, `poster.png` in order. If readable and `0 < size <= 2 MB`, return `(raw_bytes, "jpeg" | "png")`.
   - **IMDb remote fallback:** Extract `poster_url` from `(subtitle_summary or {}).get("movie_meta", {}).get("poster_url")`.
     - If present and starts with `https://` or `http://`: rewrite Amazon/IMDb suffix `re.sub(r"\._V1_.*\.(jpe?g|png)$", "._V1_UX500_.jpg", poster_url, flags=re.I)` to fetch a ~500px wide thumbnail.
     - Download with `urllib.request.urlopen(..., timeout=8)` using a Mozilla `User-Agent`.
     - Verify non-empty `<= 2 MB` and JPEG/PNG header (`\xff\xd8\xff` or `\x89PNG`), return `(raw_bytes, subtype)`.
   - On any OS/HTTP/validation error, return `None` silently (never fail email notification).

2. **`format_completion_email(job, subtitle_summary=None, warning=None, cfg=None) -> tuple[str, str]`:**
   - Parse `summary_data` from `subtitle_summary` or `job.subtitle_summary`.
   - Extract `movie_meta` (if dict) for clean `display_title` (e.g. `f"{title} ({year})"` if year not already in title, else fallback `job.name`).
   - Polish subjects:
     - Movie: `f"[torrent-drop] Pobrano (z uwagą): {display_title}"` or `f"[torrent-drop] Pobrano: {display_title}"`
     - Music: `f"[torrent-drop] Pobrano muzykę (z uwagą): {job.name}"` or `f"[torrent-drop] Pobrano muzykę: {job.name}"`
   - Polish `text/plain` body including title, category, size, destination path, info hash, Jellyfin URL (for movies when `cfg.jellyfin_url`), IMDb URL (when `imdb_id` available), and subtitle/IMDb summary.

3. **`format_completion_html(job, subtitle_summary=None, warning=None, cfg=None, has_poster=False) -> str`:**
   - Responsive table-based HTML (`max-width: 600px`), dark card palette (`#0b0f19` backdrop, `#151d2d` card, `#23314a` border, `#38bdf8` accent, `#10b981` success, `#f59e0b` warning, `#ec4899` music), inline styles only, all user/torrent values escaped with `html.escape`.
   - **Movies:** Two-column hero when `has_poster=True` (`<img src="cid:poster" width="145" ...>`), clean title/year, cast (`actors`), size pill, IMDb/subtitles summary grid in Polish, warning box if applicable, primary CTA button **Otwórz w Jellyfin** (`cfg.jellyfin_url`) and secondary button **Zobacz na IMDb** (`https://www.imdb.com/title/{imdb_id}/` when `imdb_id` present), plus technical footer (`dest_path`, `info_hash`).
   - **Music:** Music badge, album/track title, size, destination path in Navidrome, warning box if applicable.

4. **`format_failure_email(job, cfg=None) -> tuple[str, str]` & `format_failure_html(job, cfg=None) -> str`:**
   - Subject: `f"[torrent-drop] Błąd: {job.name}"`
   - Red error card in Polish showing torrent name, human-readable stage + raw state, failure reason (`job.error`), size, and info hash.

5. **`send_email(cfg, subject, body, *, html_body=None, inline_images=None) -> None`:**
   - When `html_body` is `None` and `inline_images` is empty/None: calls `msg.set_content(body)` (preserves existing plain-text behavior).
   - When `html_body` is provided:
     - `msg.set_content(body)`
     - `msg.add_alternative(html_body, subtype="html")`
     - If `inline_images`: iterate `(cid, (img_bytes, subtype))` and call `msg.get_payload()[1].add_related(img_bytes, maintype="image", subtype=subtype, cid=f"<{cid}>", filename=f"{cid}.{subtype}")`.

### 2.4 Worker Integration (`torrent-drop/app/worker.py`)

- In `_handle_completion`:
  - Completion path: resolve poster via `await asyncio.to_thread(resolve_poster_image, job, summary)`, format `(subject, body)` and `html_body` (`has_poster=poster is not None`, passing `cfg=cfg`), and send via `await asyncio.to_thread(send_email, cfg, subject, body, html_body=html_body, inline_images={"poster": poster} if poster else None)`.
  - Failure paths (`CorruptedVideoError` & `Exception`) and `_fail_metadata_timeout`: pass `html_body=format_failure_html(job, cfg=cfg)` to `send_email`.

---

## 3. Verification Plan

1. Update & expand `tests/test_fix_movies_target.py`: verify `JSON_SUMMARY` contains `movie_meta` when IMDb metadata is resolved.
2. Update & expand `tests/test_notifier.py`: test Polish completion/failure subjects and bodies, `format_completion_html` / `format_failure_html` (escaping, poster `cid:poster`, Jellyfin & IMDb CTA links), `resolve_poster_image` (local file, IMDb `._V1_UX500_.jpg` download, oversized/failure fallback to `None`), and `send_email` attaching `multipart/alternative` + `multipart/related` CID image.
3. Update & run `tests/test_postprocess_worker.py` and full `pytest` suite.
4. Send a real test email (e.g. for `Lost in Translation`) OR verify Mailgun SMTP + restart `torrent-drop.service`.
