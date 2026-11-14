import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from db import DuplicateActiveJobError, JobStore, ACTIVE_STATES
from config import Settings, load_settings


def test_job_lifecycle_and_duplicate_rules(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.db")
    store.init_schema()

    job = store.create_job("abc123", "Movie.2024", "movies", 1_000_000)
    assert job.state == "submitted"
    assert job.progress == 0.0

    with pytest.raises(DuplicateActiveJobError):
        store.create_job("abc123", "Movie.2024", "movies", 1_000_000)

    # Upper case should also be caught as duplicate active job
    with pytest.raises(DuplicateActiveJobError):
        store.create_job("ABC123", "Movie.2024", "movies", 1_000_000)

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


def test_active_states():
    expected = {"submitted", "downloading", "completed_in_client", "moving", "post_processing", "notifying"}
    assert ACTIVE_STATES == expected


def test_job_not_found(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.db")
    store.init_schema()
    assert store.get_job(9999) is None
    with pytest.raises(KeyError):
        store.update_job(9999, state="failed")
    assert store.delete_job(9999) is False


def test_settings_defaults():
    settings = load_settings(env_file=Path("/nonexistent/.env"))
    assert settings.app_port == 8088
    assert settings.gluetun_url == "http://127.0.0.1:8000"
    assert settings.qb_url == "http://127.0.0.1:8085"
    assert settings.qb_interface == "tun0"
    assert settings.downloads_dir == Path("~/projects/torrent-drop/downloads")
    assert settings.movies_dir == Path("~/projects/jellyfin/media/Movies")
    assert settings.music_dir == Path("~/projects/navidrome/music")
    assert settings.subtitle_script == Path("~/projects/jellyfin/fix_movies_subtitles_imdb.py")
    assert settings.db_path == Path("~/projects/torrent-drop/data/jobs.db")
    assert settings.smtp_host == "smtp.eu.mailgun.org"
    assert settings.smtp_port == 587
    assert settings.notify_to == "contact@marzeta.pl"
    assert isinstance(settings.allowed_subnets, list)


def test_settings_custom_env(tmp_path: Path):
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "APP_PORT=9099\n"
        "GLUETUN_URL=http://localhost:8001\n"
        "QB_URL=http://localhost:8086\n"
        "QB_USER=customuser\n"
        "QB_PASSWORD=custompass\n"
        "QB_INTERFACE=wg0\n"
        "DOWNLOADS_DIR=/custom/downloads\n"
        "MOVIES_DIR=/custom/movies\n"
        "MUSIC_DIR=/custom/music\n"
        "SUBTITLE_SCRIPT=/custom/script.py\n"
        "DB_PATH=/custom/jobs.db\n"
        "SMTP_HOST=custom.smtp.org\n"
        "SMTP_PORT=2525\n"
        "SMTP_USER=smtpuser\n"
        "SMTP_PASSWORD=smtppass\n"
        "NOTIFY_FROM=sender@custom.org\n"
        "NOTIFY_TO=recipient@custom.org\n"
        "ALLOWED_SUBNETS=10.0.0.0/8, 192.0.2.10/24\n"
        "JELLYFIN_URL=http://jellyfin.local:8096\n"
        "JELLYFIN_API_KEY=testkey123\n"
    )
    settings = load_settings(env_file=env_file)
    assert settings.app_port == 9099
    assert settings.gluetun_url == "http://localhost:8001"
    assert settings.qb_url == "http://localhost:8086"
    assert settings.qb_user == "customuser"
    assert settings.qb_password == "custompass"
    assert settings.qb_interface == "wg0"
    assert settings.downloads_dir == Path("/custom/downloads")
    assert settings.movies_dir == Path("/custom/movies")
    assert settings.music_dir == Path("/custom/music")
    assert settings.subtitle_script == Path("/custom/script.py")
    assert settings.db_path == Path("/custom/jobs.db")
    assert settings.smtp_host == "custom.smtp.org"
    assert settings.smtp_port == 2525
    assert settings.smtp_user == "smtpuser"
    assert settings.smtp_password == "smtppass"
    assert settings.notify_from == "sender@custom.org"
    assert settings.notify_to == "recipient@custom.org"
    assert settings.allowed_subnets == ["10.0.0.0/8", "192.0.2.10/24"]
    assert settings.jellyfin_url == "http://jellyfin.local:8096"
    assert settings.jellyfin_api_key == "testkey123"
