from __future__ import annotations

import contextlib
from email.message import EmailMessage
import html
import json
from pathlib import Path
import re
import smtplib
import sqlite3
import time
from typing import Any
import urllib.request

from config import Settings
from db import JobRecord

_MAX_POSTER_BYTES = 2 * 1024 * 1024
_USER_AGENT = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_DEFAULT_JELLYFIN_URL = "https://jellyfin.marzeta.pl"

_STAGE_LABELS_PL = {
    "submitted": "Wysłano do klienta",
    "downloading": "Pobieranie (lub metadane magnet)",
    "completed_in_client": "Pobrano w qBittorrent",
    "moving": "Przenoszenie do biblioteki",
    "post_processing": "Przetwarzanie napisów i IMDb",
    "failed": "Błąd",
}


def _format_size(size_bytes: int) -> str:
    """Format byte count into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    num = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num) < 1024.0:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} PB"


def _parse_summary_data(
    job: JobRecord,
    subtitle_summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if isinstance(subtitle_summary, dict):
        return subtitle_summary
    if job.subtitle_summary:
        try:
            parsed = json.loads(job.subtitle_summary)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _display_movie_title(job: JobRecord, movie_meta: dict[str, Any] | None) -> str:
    if not isinstance(movie_meta, dict):
        return job.name
    title = str(movie_meta.get("title") or "").strip()
    year = movie_meta.get("year")
    if not title:
        return job.name
    if year and str(year) not in title:
        return f"{title} ({year})"
    return title


def _imdb_url_from_meta(movie_meta: dict[str, Any] | None) -> str | None:
    if not isinstance(movie_meta, dict):
        return None
    imdb_id = str(movie_meta.get("imdb_id") or "").strip()
    if re.fullmatch(r"tt\d{6,10}", imdb_id):
        return f"https://www.imdb.com/title/{imdb_id}/"
    return None


def _jellyfin_url(cfg: Settings | None) -> str | None:
    if cfg is None:
        return f"{_DEFAULT_JELLYFIN_URL}/"
    if not cfg.jellyfin_url:
        return None
    return cfg.jellyfin_url.rstrip("/") + "/"


def _escape_sql_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _fetch_jellyfin_server_id(local_url: str) -> str | None:
    url = f"{local_url.rstrip('/')}/System/Info/Public"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read(65536).decode("utf-8"))
        srv_id = str(payload.get("Id") or "").strip()
        return srv_id or None
    except Exception:
        return None


def resolve_jellyfin_item_url(
    job: JobRecord,
    cfg: Settings | None,
    *,
    retry_attempts: int = 45,
    retry_delay_sec: float = 2.0,
) -> str | None:
    """Resolve the direct Jellyfin web URL for a completed movie, falling back to base URL."""
    base_url = _jellyfin_url(cfg)
    if not base_url or cfg is None:
        return base_url
    if (job.category or "").strip().lower() not in ("movies", "movie") or not job.dest_path:
        return base_url

    db_path = cfg.jellyfin_db_path
    if not db_path.is_file():
        return base_url

    try:
        rel_path = Path(job.dest_path).resolve().relative_to(cfg.movies_dir.resolve()).as_posix()
    except ValueError:
        return base_url

    container_path = f"/media/Movies/{rel_path}".rstrip("/")
    like_pattern = f"{_escape_sql_like(container_path)}/%"

    item_guid: str | None = None
    attempts = max(1, retry_attempts)
    uri = f"file:{db_path}?mode=ro"
    query = (
        "SELECT Id FROM BaseItems "
        "WHERE Type = 'MediaBrowser.Controller.Entities.Movies.Movie' "
        "AND (Path = ? OR Path LIKE ? ESCAPE '\\') "
        "LIMIT 1"
    )

    for attempt in range(attempts):
        try:
            with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=2.0)) as conn:
                row = conn.execute(query, (container_path, like_pattern)).fetchone()
            if row and row[0]:
                item_guid = str(row[0]).strip()
                break
        except sqlite3.Error:
            return base_url

        if attempt + 1 < attempts and retry_delay_sec > 0:
            time.sleep(retry_delay_sec)

    if not item_guid:
        return base_url

    item_id = item_guid.replace("-", "").lower()
    base_trimmed = base_url.rstrip("/")
    server_id = _fetch_jellyfin_server_id(cfg.jellyfin_local_url)
    if server_id:
        return f"{base_trimmed}/web/#/details?id={item_id}&serverId={server_id}"
    return f"{base_trimmed}/web/#/details?id={item_id}"


def _detect_image_subtype(raw: bytes) -> str | None:
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return None


def _scale_imdb_poster_url(url: str) -> str:
    return re.sub(r"\._V1_.*\.(?:jpe?g|png)$", "._V1_UX500_.jpg", url, flags=re.IGNORECASE)


def resolve_poster_image(
    job: JobRecord,
    subtitle_summary: dict[str, Any] | None = None,
) -> tuple[bytes, str] | None:
    """Resolve movie poster bytes + subtype from local folder or IMDb poster URL."""
    if (job.category or "").strip().lower() not in ("movies", "movie"):
        return None

    if job.dest_path:
        dest = Path(job.dest_path)
        if dest.is_dir():
            for fname in ("folder.jpg", "poster.jpg", "folder.png", "poster.png"):
                candidate = dest / fname
                try:
                    if candidate.is_file() and 0 < candidate.stat().st_size <= _MAX_POSTER_BYTES:
                        raw = candidate.read_bytes()
                        subtype = _detect_image_subtype(raw)
                        if subtype:
                            return raw, subtype
                except OSError:
                    continue

    summary_data = _parse_summary_data(job, subtitle_summary)
    movie_meta = summary_data.get("movie_meta") if isinstance(summary_data, dict) else None
    poster_url = str(movie_meta.get("poster_url") or "").strip() if isinstance(movie_meta, dict) else ""
    if not poster_url or not poster_url.startswith(("https://", "http://")):
        return None

    scaled_url = _scale_imdb_poster_url(poster_url)
    try:
        req = urllib.request.Request(scaled_url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read(_MAX_POSTER_BYTES + 1)
        if not raw or len(raw) > _MAX_POSTER_BYTES:
            return None
        subtype = _detect_image_subtype(raw)
        if not subtype:
            return None
        return raw, subtype
    except Exception:
        return None


def _subtitle_status_rows(summary_data: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Build structured (label, value, color_hex) subtitle/IMDb rows."""
    rows: list[tuple[str, str, str]] = []
    imdb_ok = int(summary_data.get("imdb_ok") or 0)
    imdb_fixed = list(summary_data.get("imdb_fixed") or [])
    if imdb_fixed:
        rows.append(("IMDb ID", f"Naprawiono ({len(imdb_fixed)}): {imdb_fixed[0]}", "#38bdf8"))
    elif imdb_ok > 0:
        rows.append(("IMDb ID", "Zweryfikowano poprawnie", "#10b981"))

    subs_dl = list(summary_data.get("subs_downloaded") or [])
    subs_ext = list(summary_data.get("subs_extracted") or [])
    subs_enc = list(summary_data.get("subs_encoding_fixed") or [])
    subs_ok = int(summary_data.get("subs_already_ok") or 0)
    subs_miss = list(summary_data.get("subs_missing") or [])

    if subs_dl:
        rows.append(("Pobrane napisy", ", ".join(str(x) for x in subs_dl), "#10b981"))
    if subs_ext:
        rows.append(("Wyciągnięte napisy", ", ".join(str(x) for x in subs_ext), "#10b981"))
    if subs_enc:
        rows.append(("Kodowanie UTF-8", ", ".join(str(x) for x in subs_enc), "#38bdf8"))
    if subs_ok > 0 and not subs_dl and not subs_ext:
        rows.append(("Polskie napisy", f"Już obecne ({subs_ok})", "#10b981"))
    if subs_miss:
        rows.append(("Brakujące napisy", ", ".join(str(x) for x in subs_miss), "#f59e0b"))

    corrupted = list(summary_data.get("corrupted_videos") or [])
    if corrupted:
        rows.append(("Uszkodzone wideo", ", ".join(str(x) for x in corrupted), "#ef4444"))

    skipped = list(summary_data.get("skipped_items") or [])
    if skipped:
        rows.append(("Pominięte", ", ".join(str(x) for x in skipped), "#94a3b8"))

    return rows


def format_completion_email(
    job: JobRecord,
    subtitle_summary: dict[str, Any] | None = None,
    warning: str | None = None,
    cfg: Settings | None = None,
    jellyfin_item_url: str | None = None,
) -> tuple[str, str]:
    """Format Polish subject and plain-text body for a completed torrent download."""
    effective_warning = warning if warning is not None else job.warning
    summary_data = _parse_summary_data(job, subtitle_summary)
    movie_meta = summary_data.get("movie_meta") if isinstance(summary_data, dict) else None
    is_movie = (job.category or "").strip().lower() in ("movies", "movie")

    display_title = _display_movie_title(job, movie_meta) if is_movie else job.name
    if is_movie:
        prefix = "Pobrano (z uwagą)" if effective_warning else "Pobrano"
    else:
        prefix = "Pobrano muzykę (z uwagą)" if effective_warning else "Pobrano muzykę"
    subject = f"[torrent-drop] {prefix}: {display_title}"

    lines = [
        f"Tytuł: {display_title}",
        f"Kategoria: {'Film' if is_movie else 'Muzyka'}",
        f"Rozmiar: {_format_size(job.total_size)} ({job.total_size:,} bajtów)",
        f"Folder docelowy: {job.dest_path or 'N/A'}",
    ]

    if is_movie and isinstance(movie_meta, dict) and movie_meta.get("actors"):
        lines.append(f"Obsada: {movie_meta['actors']}")

    imdb_url = _imdb_url_from_meta(movie_meta) if is_movie else None
    jf_url = (jellyfin_item_url or _jellyfin_url(cfg)) if is_movie else None
    if jf_url:
        lines.append(f"Otwórz w Jellyfin: {jf_url}")
    if imdb_url:
        lines.append(f"IMDb: {imdb_url}")

    lines.append(f"Info Hash: {job.info_hash}")

    if effective_warning:
        lines.extend(["", f"Uwaga: {effective_warning}"])

    if is_movie and isinstance(summary_data, dict):
        rows = _subtitle_status_rows(summary_data)
        if rows:
            lines.extend(["", "=== Napisy i IMDb ==="])
            for label, value, _ in rows:
                lines.append(f"- {label}: {value}")

    return subject, "\n".join(lines) + "\n"


def format_completion_html(
    job: JobRecord,
    subtitle_summary: dict[str, Any] | None = None,
    warning: str | None = None,
    cfg: Settings | None = None,
    has_poster: bool = False,
    jellyfin_item_url: str | None = None,
) -> str:
    """Format a responsive dark-themed Polish HTML email for completed downloads."""
    effective_warning = warning if warning is not None else job.warning
    summary_data = _parse_summary_data(job, subtitle_summary)
    movie_meta = summary_data.get("movie_meta") if isinstance(summary_data, dict) else None
    is_movie = (job.category or "").strip().lower() in ("movies", "movie")

    display_title = _display_movie_title(job, movie_meta) if is_movie else job.name
    esc_title = html.escape(display_title)
    esc_size = html.escape(_format_size(job.total_size))
    esc_dest = html.escape(job.dest_path or "N/A")
    esc_hash = html.escape(job.info_hash)

    if effective_warning:
        badge_bg, badge_border, badge_fg = "rgba(245,158,11,0.18)", "#f59e0b", "#fcd34d"
        badge_text = "FILM GOTOWY (Z UWAGĄ)" if is_movie else "MUZYKA GOTOWA (Z UWAGĄ)"
    elif is_movie:
        badge_bg, badge_border, badge_fg = "rgba(16,185,129,0.18)", "#10b981", "#6ee7b7"
        badge_text = "FILM GOTOWY DO OGLĄDANIA"
    else:
        badge_bg, badge_border, badge_fg = "rgba(236,72,153,0.18)", "#ec4899", "#f9a8d4"
        badge_text = "MUZYKA GOTOWA"

    actors_html = ""
    if is_movie and isinstance(movie_meta, dict) and movie_meta.get("actors"):
        actors_html = (
            f'<div style="margin-top:8px;font-size:14px;color:#cbd5e1;">'
            f'<span style="color:#94a3b8;">Obsada:</span> {html.escape(str(movie_meta["actors"]))}'
            f"</div>"
        )

    poster_cell = ""
    if is_movie and has_poster:
        poster_cell = (
            '<td width="155" valign="top" style="padding:0 20px 12px 0;">'
            f'<img src="cid:poster" alt="{esc_title}" width="145" '
            'style="display:block;width:145px;height:auto;border-radius:10px;border:1px solid #334155;">'
            "</td>"
        )

    jf_url = (jellyfin_item_url or _jellyfin_url(cfg)) if is_movie else None
    imdb_url = _imdb_url_from_meta(movie_meta) if is_movie else None
    buttons: list[str] = []
    if jf_url:
        buttons.append(
            f'<a href="{html.escape(jf_url, quote=True)}" target="_blank" '
            'style="display:inline-block;background:#38bdf8;color:#0b0f19;text-decoration:none;'
            'font-weight:700;font-size:14px;padding:11px 18px;border-radius:9px;margin:4px 8px 4px 0;">'
            "Otwórz w Jellyfin</a>"
        )
    if imdb_url:
        buttons.append(
            f'<a href="{html.escape(imdb_url, quote=True)}" target="_blank" '
            'style="display:inline-block;background:#1e293b;color:#f1f5f9;text-decoration:none;'
            'font-weight:600;font-size:14px;padding:10px 16px;border-radius:9px;border:1px solid #334155;margin:4px 8px 4px 0;">'
            "Zobacz na IMDb</a>"
        )
    buttons_html = f'<div style="margin-top:16px;">{"".join(buttons)}</div>' if buttons else ""

    summary_html = ""
    if is_movie and isinstance(summary_data, dict):
        rows = _subtitle_status_rows(summary_data)
        if rows:
            row_items = "".join(
                f'<tr><td style="padding:7px 12px 7px 0;font-size:13px;color:#94a3b8;white-space:nowrap;" valign="top">{html.escape(lbl)}</td>'
                f'<td style="padding:7px 0;font-size:13px;color:{clr};font-weight:600;">{html.escape(val)}</td></tr>'
                for lbl, val, clr in rows
            )
            summary_html = (
                '<div style="margin-top:20px;padding:14px 16px;background:#0b0f19;border:1px solid #23314a;border-radius:10px;">'
                '<div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:#94a3b8;margin-bottom:6px;">Napisy i IMDb</div>'
                f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;">{row_items}</table>'
                "</div>"
            )

    warning_html = ""
    if effective_warning:
        warning_html = (
            '<div style="margin-top:16px;padding:12px 14px;background:rgba(245,158,11,0.12);'
            'border:1px solid #f59e0b;border-radius:10px;color:#fcd34d;font-size:13px;">'
            f'<strong>Uwaga:</strong> {html.escape(effective_warning)}</div>'
        )

    hero_html = (
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;"><tr>'
        f"{poster_cell}"
        '<td valign="top">'
        f'<div style="font-size:22px;font-weight:700;line-height:1.25;color:#f8fafc;">{esc_title}</div>'
        f"{actors_html}"
        '<div style="margin-top:12px;">'
        f'<span style="display:inline-block;background:#0b0f19;border:1px solid #23314a;color:#cbd5e1;font-size:12px;font-weight:600;padding:4px 10px;border-radius:999px;margin-right:6px;">{esc_size}</span>'
        f'<span style="display:inline-block;background:#0b0f19;border:1px solid #23314a;color:#cbd5e1;font-size:12px;font-weight:600;padding:4px 10px;border-radius:999px;">{"Jellyfin · Movies" if is_movie else "Navidrome · Music"}</span>'
        "</div>"
        f"{buttons_html}"
        "</td></tr></table>"
    )

    footer_html = (
        '<div style="margin-top:18px;padding-top:14px;border-top:1px solid #23314a;font-size:12px;color:#64748b;word-break:break-all;">'
        f"<div><strong>Folder:</strong> {esc_dest}</div>"
        f'<div style="margin-top:4px;"><strong>Hash:</strong> {esc_hash}</div>'
        "</div>"
    )

    return _wrap_html_card(
        badge_text=badge_text,
        badge_bg=badge_bg,
        badge_border=badge_border,
        badge_fg=badge_fg,
        inner_html=hero_html + summary_html + warning_html + footer_html,
    )


def format_failure_email(job: JobRecord, cfg: Settings | None = None) -> tuple[str, str]:
    """Format Polish subject and plain-text body for a failed torrent download."""
    del cfg  # Reserved for consistent signature across formatters
    subject = f"[torrent-drop] Błąd: {job.name}"
    stage_pl = _STAGE_LABELS_PL.get(job.state, job.state)

    lines = [
        f"Torrent: {job.name}",
        f"Kategoria: {job.category}",
        f"Etap: {stage_pl} ({job.state})",
        f"Rozmiar: {_format_size(job.total_size)} ({job.total_size:,} bajtów)",
        f"Info Hash: {job.info_hash}",
    ]
    if job.dest_path:
        lines.append(f"Folder docelowy: {job.dest_path}")

    lines.extend(["", "Powód błędu:", job.error or "Nieznany błąd"])

    if job.warning:
        lines.extend(["", f"Uwaga: {job.warning}"])

    return subject, "\n".join(lines) + "\n"


def format_failure_html(job: JobRecord, cfg: Settings | None = None) -> str:
    """Format a responsive dark-themed Polish HTML email for failed downloads."""
    del cfg
    stage_pl = _STAGE_LABELS_PL.get(job.state, job.state)
    inner = (
        f'<div style="font-size:20px;font-weight:700;color:#f8fafc;word-break:break-word;">{html.escape(job.name)}</div>'
        '<div style="margin-top:10px;font-size:13px;color:#94a3b8;">'
        f'Etap: <strong style="color:#e2e8f0;">{html.escape(stage_pl)}</strong> ({html.escape(job.state)}) · '
        f'Rozmiar: {html.escape(_format_size(job.total_size))}'
        "</div>"
        '<div style="margin-top:16px;padding:14px 16px;background:rgba(239,68,68,0.12);'
        'border:1px solid #ef4444;border-radius:10px;color:#fecaca;font-size:14px;word-break:break-word;">'
        f'<strong>Powód błędu:</strong><br>{html.escape(job.error or "Nieznany błąd")}'
        "</div>"
        '<div style="margin-top:16px;padding-top:12px;border-top:1px solid #23314a;font-size:12px;color:#64748b;word-break:break-all;">'
        f'<strong>Hash:</strong> {html.escape(job.info_hash)}'
        "</div>"
    )
    return _wrap_html_card(
        badge_text="BŁĄD POBIERANIA",
        badge_bg="rgba(239,68,68,0.18)",
        badge_border="#ef4444",
        badge_fg="#fca5a5",
        inner_html=inner,
    )


def _wrap_html_card(
    badge_text: str,
    badge_bg: str,
    badge_border: str,
    badge_fg: str,
    inner_html: str,
) -> str:
    return (
        '<!DOCTYPE html><html lang="pl"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0"></head>'
        '<body style="margin:0;padding:24px 12px;background:#0b0f19;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;color:#f1f5f9;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;margin:0 auto;'
        'background:#151d2d;border:1px solid #23314a;border-radius:14px;overflow:hidden;">'
        '<tr><td style="padding:22px 24px;">'
        '<div style="margin-bottom:16px;">'
        f'<span style="display:inline-block;background:{badge_bg};border:1px solid {badge_border};color:{badge_fg};'
        f'font-size:11px;font-weight:700;letter-spacing:0.6px;padding:4px 10px;border-radius:999px;">{html.escape(badge_text)}</span>'
        '<span style="float:right;font-size:12px;font-weight:600;color:#64748b;padding-top:4px;">torrent-drop</span>'
        "</div>"
        f"{inner_html}"
        "</td></tr></table></body></html>"
    )


def send_email(
    cfg: Settings,
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
    inline_images: dict[str, tuple[bytes, str]] | None = None,
) -> None:
    """Send an email notification via SMTP (plain text or rich HTML + inline CID images)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.notify_from
    msg["To"] = cfg.notify_to
    msg.set_content(body)

    if html_body is not None:
        msg.add_alternative(html_body, subtype="html")
        if inline_images:
            html_part = msg.get_payload()[1]
            for cid, (img_bytes, subtype) in inline_images.items():
                html_part.add_related(
                    img_bytes,
                    maintype="image",
                    subtype=subtype,
                    cid=f"<{cid}>",
                    filename=f"{cid}.{subtype}",
                )

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
        server.starttls()
        if cfg.smtp_user:
            server.login(cfg.smtp_user, cfg.smtp_password)
        server.send_message(msg)
