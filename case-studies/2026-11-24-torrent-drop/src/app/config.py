from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    app_port: int = 8088
    gluetun_url: str = "http://127.0.0.1:8000"
    qb_url: str = "http://127.0.0.1:8085"
    qb_user: str = "admin"
    qb_password: str = "adminadmin"
    qb_interface: str = "tun0"
    downloads_dir: Path = field(default_factory=lambda: Path("~/projects/torrent-drop/downloads"))
    movies_dir: Path = field(default_factory=lambda: Path("~/projects/jellyfin/media/Movies"))
    music_dir: Path = field(default_factory=lambda: Path("~/projects/navidrome/music"))
    subtitle_script: Path = field(default_factory=lambda: Path("~/projects/jellyfin/fix_movies_subtitles_imdb.py"))
    db_path: Path = field(default_factory=lambda: Path("~/projects/torrent-drop/data/jobs.db"))
    smtp_host: str = "smtp.eu.mailgun.org"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notify_from: str = "torrent-drop@marzeta.pl"
    notify_to: str = "contact@marzeta.pl"
    allowed_subnets: list[str] = field(default_factory=list)
    jellyfin_url: str | None = "https://jellyfin.marzeta.pl"
    jellyfin_api_key: str | None = None
    jellyfin_local_url: str = "http://127.0.0.1:8096"
    jellyfin_db_path: Path = field(
        default_factory=lambda: Path("~/projects/jellyfin/config/data/jellyfin.db")
    )
    magnet_metadata_timeout_sec: int = 900


def parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return env

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        env[key] = val
    return env


def load_settings(env_file: Path | None = None) -> Settings:
    file_vars: dict[str, str] = {}
    if env_file is not None:
        file_vars = parse_env_file(env_file)
    else:
        default_env = Path(__file__).resolve().parents[1] / ".env"
        if default_env.is_file():
            file_vars = parse_env_file(default_env)

    def get_var(name: str, default: str | None = None) -> str | None:
        if name in os.environ:
            return os.environ[name]
        if name in file_vars:
            return file_vars[name]
        return default

    # Port
    app_port_raw = get_var("APP_PORT", "8088")
    try:
        app_port = int(app_port_raw) if app_port_raw is not None else 8088
    except ValueError:
        app_port = 8088

    # URLs
    gluetun_url = get_var("GLUETUN_URL", "http://127.0.0.1:8000") or "http://127.0.0.1:8000"
    qb_url = get_var("QB_URL", "http://127.0.0.1:8085") or "http://127.0.0.1:8085"

    # qBittorrent auth & interface
    qb_user = get_var("QB_USER", "admin") or "admin"
    qb_password = get_var("QB_PASSWORD", "adminadmin") or "adminadmin"
    qb_interface = get_var("QB_INTERFACE", "tun0") or "tun0"

    # Paths
    downloads_dir = Path(get_var("DOWNLOADS_DIR", "~/projects/torrent-drop/downloads") or "~/projects/torrent-drop/downloads")
    movies_dir = Path(get_var("MOVIES_DIR", "~/projects/jellyfin/media/Movies") or "~/projects/jellyfin/media/Movies")
    music_dir = Path(get_var("MUSIC_DIR", "~/projects/navidrome/music") or "~/projects/navidrome/music")
    subtitle_script = Path(get_var("SUBTITLE_SCRIPT", "~/projects/jellyfin/fix_movies_subtitles_imdb.py") or "~/projects/jellyfin/fix_movies_subtitles_imdb.py")
    db_path = Path(get_var("DB_PATH", "~/projects/torrent-drop/data/jobs.db") or "~/projects/torrent-drop/data/jobs.db")

    # SMTP
    smtp_host = get_var("SMTP_HOST", "smtp.eu.mailgun.org") or "smtp.eu.mailgun.org"
    smtp_port_raw = get_var("SMTP_PORT", "587")
    try:
        smtp_port = int(smtp_port_raw) if smtp_port_raw is not None else 587
    except ValueError:
        smtp_port = 587
    smtp_user = get_var("SMTP_USER", "") or ""
    smtp_password = get_var("SMTP_PASSWORD", "") or ""
    notify_from = get_var("NOTIFY_FROM", "torrent-drop@marzeta.pl") or "torrent-drop@marzeta.pl"
    notify_to = get_var("NOTIFY_TO", "contact@marzeta.pl") or "contact@marzeta.pl"

    # Subnets
    raw_subnets = get_var("ALLOWED_SUBNETS", "") or ""
    allowed_subnets = [s.strip() for s in raw_subnets.split(",") if s.strip()]

    # Jellyfin
    jellyfin_url = get_var("JELLYFIN_URL", "https://jellyfin.marzeta.pl")
    if jellyfin_url == "":
        jellyfin_url = None
    jellyfin_api_key = get_var("JELLYFIN_API_KEY", None)
    if jellyfin_api_key == "":
        jellyfin_api_key = None
    jellyfin_local_url = get_var("JELLYFIN_LOCAL_URL", "http://127.0.0.1:8096") or "http://127.0.0.1:8096"
    jellyfin_db_path = Path(
        get_var("JELLYFIN_DB_PATH", "~/projects/jellyfin/config/data/jellyfin.db")
        or "~/projects/jellyfin/config/data/jellyfin.db"
    )

    # Magnet metadata timeout
    timeout_raw = get_var("MAGNET_METADATA_TIMEOUT_SEC", "900")
    try:
        magnet_metadata_timeout_sec = int(timeout_raw) if timeout_raw is not None else 900
    except ValueError:
        magnet_metadata_timeout_sec = 900

    return Settings(
        app_port=app_port,
        gluetun_url=gluetun_url,
        qb_url=qb_url,
        qb_user=qb_user,
        qb_password=qb_password,
        qb_interface=qb_interface,
        downloads_dir=downloads_dir,
        movies_dir=movies_dir,
        music_dir=music_dir,
        subtitle_script=subtitle_script,
        db_path=db_path,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        notify_from=notify_from,
        notify_to=notify_to,
        allowed_subnets=allowed_subnets,
        jellyfin_url=jellyfin_url,
        jellyfin_api_key=jellyfin_api_key,
        jellyfin_local_url=jellyfin_local_url,
        jellyfin_db_path=jellyfin_db_path,
        magnet_metadata_timeout_sec=magnet_metadata_timeout_sec,
    )
