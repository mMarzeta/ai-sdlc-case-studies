from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
import sys
from unittest import mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from config import Settings
from db import JobRecord
from notifier import (
    format_completion_email,
    format_completion_html,
    format_failure_email,
    format_failure_html,
    resolve_jellyfin_item_url,
    resolve_poster_image,
    send_email,
)


def make_job(
    id: int = 1,
    info_hash: str = "abcdef1234567890abcdef1234567890abcdef12",
    name: str = "Dune Part Two (2024)",
    category: str = "movies",
    total_size: int = 15_000_000_000,
    state: str = "done",
    progress: float = 1.0,
    dlspeed: int = 0,
    eta: int = 0,
    content_path: str | None = "/downloads/complete/movies/Dune Part Two (2024)",
    dest_path: str | None = "~/projects/jellyfin/media/Movies/Dune Part Two (2024)",
    subtitle_summary: str | None = None,
    warning: str | None = None,
    error: str | None = None,
) -> JobRecord:
    return JobRecord(
        id=id,
        info_hash=info_hash,
        name=name,
        category=category,
        total_size=total_size,
        state=state,
        progress=progress,
        dlspeed=dlspeed,
        eta=eta,
        content_path=content_path,
        dest_path=dest_path,
        subtitle_summary=subtitle_summary,
        warning=warning,
        error=error,
    )


def test_format_completion_email_movies_with_meta_subtitles_and_warning():
    job = make_job(
        name="Dune.Part.Two.2024.1080p.BluRay.x265-GRP",
        category="movies",
        total_size=15_000_000_000,
        dest_path="~/projects/jellyfin/media/Movies/Dune Part Two (2024)",
    )
    sub_summary = {
        "imdb_ok": 1,
        "imdb_fixed": ["Fixed IMDb ID: tt15239678"],
        "subs_downloaded": ["Dune.Part.Two.2024.pol.srt"],
        "subs_extracted": ["track 2 (pl)"],
        "subs_encoding_fixed": ["Dune.Part.Two.2024.pol.srt (CP1250 -> UTF-8)"],
        "subs_already_ok": 0,
        "subs_missing": [],
        "corrupted_videos": [],
        "skipped_items": [],
        "movie_meta": {
            "imdb_id": "tt15239678",
            "title": "Dune: Part Two",
            "year": 2024,
            "actors": "Timothee Chalamet, Zendaya",
            "poster_url": "https://m.media-amazon.com/images/M/dune._V1_.jpg",
        },
    }
    warning_text = "NapiProjekt rate limit delayed search by 15s"
    cfg = Settings(jellyfin_url="https://jellyfin.marzeta.pl")

    subject, body = format_completion_email(
        job, subtitle_summary=sub_summary, warning=warning_text, cfg=cfg
    )

    assert "Pobrano (z uwagą):" in subject
    assert "Dune: Part Two (2024)" in subject
    assert "Dune: Part Two (2024)" in body
    assert "Timothee Chalamet, Zendaya" in body
    assert "https://jellyfin.marzeta.pl" in body
    assert "https://www.imdb.com/title/tt15239678/" in body
    assert "~/projects/jellyfin/media/Movies/Dune Part Two (2024)" in body
    assert "13.97 GB" in body
    assert "Dune.Part.Two.2024.pol.srt" in body
    assert "track 2 (pl)" in body
    assert "CP1250 -> UTF-8" in body
    assert warning_text in body


def test_format_completion_email_movies_with_missing_subs_and_record_warning():
    job = make_job(
        name="Arrival (2016)",
        category="movies",
        total_size=8_500_000_000,
        dest_path="~/projects/jellyfin/media/Movies/Arrival (2016)",
        warning="Subtitle script exited with code 1",
    )
    sub_summary = {
        "imdb_ok": 0,
        "imdb_fixed": [],
        "subs_downloaded": [],
        "subs_extracted": [],
        "subs_encoding_fixed": [],
        "subs_already_ok": 0,
        "subs_missing": ["Arrival (2016) (no Polish subs found)"],
        "corrupted_videos": [],
        "skipped_items": [],
    }

    subject, body = format_completion_email(job, subtitle_summary=sub_summary, warning=None)

    assert "Pobrano (z uwagą): Arrival (2016)" in subject
    assert "Arrival (2016)" in body
    assert "no Polish subs found" in body
    assert "Subtitle script exited with code 1" in body


def test_format_completion_email_movies_no_subtitles():
    job = make_job(
        name="Oppenheimer (2023)",
        category="movies",
        total_size=25_000_000_000,
        dest_path="~/projects/jellyfin/media/Movies/Oppenheimer (2023)",
    )

    subject, body = format_completion_email(job, subtitle_summary=None, warning=None)

    assert "Pobrano: Oppenheimer (2023)" in subject
    assert "~/projects/jellyfin/media/Movies/Oppenheimer (2023)" in body


def test_format_completion_email_music():
    job = make_job(
        name="Pink Floyd - The Dark Side of the Moon (1973) [FLAC]",
        category="music",
        total_size=450_000_000,
        dest_path="~/projects/navidrome/music/Pink Floyd - The Dark Side of the Moon (1973) [FLAC]",
    )

    subject, body = format_completion_email(job, subtitle_summary=None)

    assert "Pobrano muzykę: Pink Floyd - The Dark Side of the Moon (1973) [FLAC]" in subject
    assert "~/projects/navidrome/music/Pink Floyd - The Dark Side of the Moon (1973) [FLAC]" in body
    assert "NapiProjekt" not in body
    assert "napisy" not in body.lower()


def test_format_failure_email():
    job = make_job(
        name="Corrupted Movie (2024)",
        category="movies",
        state="post_processing",
        total_size=1_200_000_000,
        error="Corrupted video file: /downloads/complete/movies/Corrupted.mp4",
    )

    subject, body = format_failure_email(job)

    assert "Błąd: Corrupted Movie (2024)" in subject
    assert "Corrupted Movie (2024)" in body
    assert "post_processing" in body
    assert "Corrupted video file: /downloads/complete/movies/Corrupted.mp4" in body


def test_format_completion_html_poster_links_and_escaping():
    job = make_job(
        name="Lost <script>alert(1)</script>",
        category="movies",
        total_size=5_586_939_038,
        dest_path="~/projects/jellyfin/media/Movies/Lost.In.Translation.2003",
    )
    sub_summary = {
        "imdb_ok": 1,
        "imdb_fixed": [],
        "subs_downloaded": ["movie.pol.srt"],
        "subs_extracted": [],
        "subs_encoding_fixed": [],
        "subs_already_ok": 0,
        "subs_missing": [],
        "corrupted_videos": [],
        "skipped_items": [],
        "movie_meta": {
            "imdb_id": "tt0335266",
            "title": "Lost in Translation",
            "year": 2003,
            "actors": "Bill Murray, Scarlett Johansson",
            "poster_url": "https://m.media-amazon.com/images/M/test._V1_.jpg",
        },
    }
    cfg = Settings(jellyfin_url="https://jellyfin.marzeta.pl/")

    html_with_poster = format_completion_html(
        job, subtitle_summary=sub_summary, cfg=cfg, has_poster=True
    )
    assert 'src="cid:poster"' in html_with_poster
    assert "Lost in Translation (2003)" in html_with_poster
    assert "Bill Murray, Scarlett Johansson" in html_with_poster
    assert "https://jellyfin.marzeta.pl/" in html_with_poster
    assert "https://www.imdb.com/title/tt0335266/" in html_with_poster
    assert "<script>" not in html_with_poster

    html_no_meta = format_completion_html(job, subtitle_summary=None, cfg=cfg, has_poster=False)
    assert "<script>" not in html_no_meta
    assert "&lt;script&gt;" in html_no_meta

    html_no_poster = format_completion_html(
        job, subtitle_summary=sub_summary, cfg=cfg, has_poster=False
    )
    assert 'src="cid:poster"' not in html_no_poster

    fail_html = format_failure_html(
        make_job(name="Bad<tag>", state="failed", error="Boom <err>"), cfg=cfg
    )
    assert "Bad&lt;tag&gt;" in fail_html
    assert "Boom &lt;err&gt;" in fail_html


def test_resolve_poster_image_local_and_imdb_remote(tmp_path: Path):
    movie_dir = tmp_path / "Lost.In.Translation.2003"
    movie_dir.mkdir()
    fake_jpeg = b"\xff\xd8\xff\xe0" + (b"\x00" * 32)
    (movie_dir / "folder.jpg").write_bytes(fake_jpeg)

    job_local = make_job(dest_path=str(movie_dir))
    resolved = resolve_poster_image(job_local, None)
    assert resolved == (fake_jpeg, "jpeg")

    # Empty folder falls back to IMDb poster_url rewritten to _V1_UX500_.jpg
    empty_dir = tmp_path / "NoPoster"
    empty_dir.mkdir()
    job_remote = make_job(dest_path=str(empty_dir))
    summary = {
        "movie_meta": {
            "imdb_id": "tt0335266",
            "title": "Lost in Translation",
            "year": 2003,
            "poster_url": "https://m.media-amazon.com/images/M/MV5BMTUx._V1_.jpg",
        }
    }

    requested_urls: list[str] = []

    class FakeResp:
        headers = {"Content-Type": "image/jpeg"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n: int = -1):
            return fake_jpeg

    def fake_urlopen(req, timeout=8):
        requested_urls.append(req.full_url)
        return FakeResp()

    with mock.patch("notifier.urllib.request.urlopen", side_effect=fake_urlopen):
        res_remote = resolve_poster_image(job_remote, summary)

    assert res_remote == (fake_jpeg, "jpeg")
    assert requested_urls == ["https://m.media-amazon.com/images/M/MV5BMTUx._V1_UX500_.jpg"]

    # Network error returns None without raising
    with mock.patch("notifier.urllib.request.urlopen", side_effect=OSError("timeout")):
        assert resolve_poster_image(job_remote, summary) is None


def test_send_email_plain_and_html_with_inline_poster():
    cfg = Settings(
        smtp_host="smtp.eu.mailgun.org",
        smtp_port=587,
        smtp_user="postmaster@marzeta.pl",
        smtp_password="supersecretpassword",
        notify_from="torrent-drop@marzeta.pl",
        notify_to="contact@marzeta.pl",
    )

    with mock.patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = mock_smtp_cls.return_value.__enter__.return_value
        send_email(cfg, "Test Subject", "Test Body Message")
        sent_msg: EmailMessage = mock_server.send_message.call_args[0][0]
        assert sent_msg["Subject"] == "Test Subject"
        assert sent_msg.get_content().strip() == "Test Body Message"

    fake_jpeg = b"\xff\xd8\xff\xe0" + (b"\x00" * 16)
    with mock.patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = mock_smtp_cls.return_value.__enter__.return_value
        send_email(
            cfg,
            "HTML Subject",
            "Plain fallback",
            html_body="<html><body><img src='cid:poster'></body></html>",
            inline_images={"poster": (fake_jpeg, "jpeg")},
        )
        sent_msg = mock_server.send_message.call_args[0][0]
        assert sent_msg.is_multipart()
        raw = sent_msg.as_string()
        assert "Plain fallback" in raw
        assert "cid:poster" in raw
        assert "Content-ID: <poster>" in raw


def test_send_email_without_auth():
    cfg = Settings(
        smtp_host="smtp.local",
        smtp_port=1025,
        smtp_user="",
        smtp_password="",
        notify_from="torrent-drop@marzeta.pl",
        notify_to="contact@marzeta.pl",
    )

    with mock.patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = mock_smtp_cls.return_value.__enter__.return_value
        send_email(cfg, "Local Subject", "Local Body")
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_not_called()
        mock_server.send_message.assert_called_once()


def test_send_email_error_propagates():
    cfg = Settings(
        smtp_host="smtp.eu.mailgun.org",
        smtp_port=587,
        smtp_user="user",
        smtp_password="pw",
    )

    with mock.patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = OSError("Connection refused")
        with pytest.raises(OSError, match="Connection refused"):
            send_email(cfg, "Subject", "Body")


def test_resolve_jellyfin_item_url_and_formatters(tmp_path: Path):
    import sqlite3

    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    jf_db = tmp_path / "jellyfin.db"
    with sqlite3.connect(str(jf_db)) as conn:
        conn.execute("CREATE TABLE BaseItems (Id TEXT, Name TEXT, Path TEXT, Type TEXT)")
        # Extra inside same folder must NOT match ahead of the Movie row
        conn.execute(
            "INSERT INTO BaseItems VALUES (?, ?, ?, ?)",
            (
                "02E81A9A-63D9-B26F-C27D-2B3C8C952E8F",
                "Deleted Scenes",
                "/media/Movies/Lost.In.Translation.2003/Extras/Deleted Scenes.mkv",
                "MediaBrowser.Controller.Entities.Video",
            ),
        )
        conn.execute(
            "INSERT INTO BaseItems VALUES (?, ?, ?, ?)",
            (
                "8660679E-E15E-901B-4D66-4534A8C4E9E7",
                "Lost in Translation",
                "/media/Movies/Lost.In.Translation.2003/Lost.In.Translation.2003.mkv",
                "MediaBrowser.Controller.Entities.Movies.Movie",
            ),
        )
        conn.commit()

    cfg = Settings(
        movies_dir=movies_dir,
        jellyfin_url="https://jellyfin.marzeta.pl/",
        jellyfin_local_url="http://127.0.0.1:8096",
        jellyfin_db_path=jf_db,
    )
    job = make_job(dest_path=str(movies_dir / "Lost.In.Translation.2003"))

    class FakeServerInfoResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n: int = -1):
            return b'{"Id": "8f61a62dbefd486fbf3bce0e8c4c1bd8"}'

    with mock.patch("notifier.urllib.request.urlopen", return_value=FakeServerInfoResp()):
        url = resolve_jellyfin_item_url(job, cfg, retry_attempts=1, retry_delay_sec=0.0)

    expected_url = (
        "https://jellyfin.marzeta.pl/web/#/details"
        "?id=8660679ee15e901b4d664534a8c4e9e7&serverId=8f61a62dbefd486fbf3bce0e8c4c1bd8"
    )
    assert url == expected_url

    # Server info unreachable still produces direct item details URL without serverId
    with mock.patch("notifier.urllib.request.urlopen", side_effect=OSError("down")):
        url_no_srv = resolve_jellyfin_item_url(job, cfg, retry_attempts=1, retry_delay_sec=0.0)
    assert url_no_srv == "https://jellyfin.marzeta.pl/web/#/details?id=8660679ee15e901b4d664534a8c4e9e7"

    # Unindexed movie falls back cleanly to base Jellyfin URL
    missing_job = make_job(dest_path=str(movies_dir / "NotIndexedYet (2025)"))
    assert (
        resolve_jellyfin_item_url(missing_job, cfg, retry_attempts=1, retry_delay_sec=0.0)
        == "https://jellyfin.marzeta.pl/"
    )

    # Formatters render the exact jellyfin_item_url
    import html as _html

    _, body = format_completion_email(job, cfg=cfg, jellyfin_item_url=expected_url)
    html_out = format_completion_html(job, cfg=cfg, jellyfin_item_url=expected_url)
    assert expected_url in body
    assert _html.escape(expected_url, quote=True) in html_out
