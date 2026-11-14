from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import sys
from unittest import mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from config import Settings
from db import JobStore
from postprocess import (
    CorruptedVideoError,
    PostProcessError,
    cleanup_target,
    map_container_path,
    move_to_library,
    run_subtitle_script,
)
from torrent_client import TorrentProgress
from worker import poll_once, run_worker_loop


# ---------------------------------------------------------------------------
# Test Helpers & Fakes
# ---------------------------------------------------------------------------


class FakeQBittorrentClient:
    def __init__(self, torrents: dict[str, TorrentProgress] | None = None) -> None:
        self.torrents: dict[str, TorrentProgress] = torrents or {}
        self.deleted_torrents: list[tuple[str, bool]] = []

    async def get_torrents(self, hashes: list[str]) -> dict[str, TorrentProgress]:
        result = {}
        for h in hashes:
            if h in self.torrents:
                result[h] = self.torrents[h]
            if h.lower() in self.torrents:
                result[h.lower()] = self.torrents[h.lower()]
        return result

    async def delete_torrent(self, info_hash: str, delete_files: bool = False) -> None:
        self.deleted_torrents.append((info_hash, delete_files))
        self.torrents.pop(info_hash, None)
        self.torrents.pop(info_hash.lower(), None)


def create_fake_script(path: Path, code: str) -> Path:
    path.write_text(code, encoding="utf-8")
    path.chmod(0o755)
    return path


# ---------------------------------------------------------------------------
# PostProcess Unit Tests
# ---------------------------------------------------------------------------


def test_map_container_path_valid(tmp_path: Path):
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()

    mapped = map_container_path("/downloads/complete/movies/Dune (2021)/dune.mkv", dl_dir)
    assert mapped == (dl_dir / "complete/movies/Dune (2021)/dune.mkv").resolve()


def test_map_container_path_traversal_and_invalid(tmp_path: Path):
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()

    with pytest.raises(PostProcessError, match="does not start with '/downloads/'"):
        map_container_path("/etc/shadow", dl_dir)

    with pytest.raises(PostProcessError, match="Path traversal|downloads root"):
        map_container_path("/downloads/../../etc/shadow", dl_dir)

    with pytest.raises(PostProcessError, match="Path traversal|downloads root"):
        map_container_path("/downloads/", dl_dir)


def test_move_to_library_file_and_directory(tmp_path: Path):
    dest_dir = tmp_path / "movies"
    src_file = tmp_path / "staging_movie.mkv"
    src_file.write_bytes(b"video data")

    # Move single file
    moved_file = move_to_library(src_file, dest_dir)
    assert moved_file == dest_dir / "staging_movie.mkv"
    assert moved_file.is_file()
    assert not src_file.exists()

    # Move directory
    src_folder = tmp_path / "staging_folder (2024)"
    src_folder.mkdir()
    (src_folder / "part1.mkv").write_bytes(b"part1")
    moved_folder = move_to_library(src_folder, dest_dir)
    assert moved_folder == dest_dir / "staging_folder (2024)"
    assert (moved_folder / "part1.mkv").is_file()
    assert not src_folder.exists()


def test_move_to_library_collision_raises(tmp_path: Path):
    dest_dir = tmp_path / "movies"
    dest_dir.mkdir()
    existing = dest_dir / "Collision.mkv"
    existing.write_bytes(b"existing")

    src = tmp_path / "Collision.mkv"
    src.write_bytes(b"new")

    with pytest.raises(PostProcessError, match="already exists"):
        move_to_library(src, dest_dir)

    assert src.is_file()
    assert existing.read_bytes() == b"existing"


def test_move_to_library_already_moved_recovery(tmp_path: Path):
    dest_dir = tmp_path / "movies"
    dest_dir.mkdir()
    already_moved = dest_dir / "Recovered (2024)"
    already_moved.mkdir()
    (already_moved / "movie.mkv").write_bytes(b"recovered")

    # Missing from source (already moved)
    src = tmp_path / "downloads" / "Recovered (2024)"

    # With allow_already_moved=True and src not existing: returns dest
    res = move_to_library(src, dest_dir, allow_already_moved=True)
    assert res == already_moved
    assert res.exists()

    # With allow_already_moved=False and src not existing: raises PostProcessError
    with pytest.raises(PostProcessError, match="does not exist"):
        move_to_library(src, dest_dir, allow_already_moved=False)

    # With allow_already_moved=True but both src and dest existing: still raises collision
    src.mkdir(parents=True)
    (src / "movie.mkv").write_bytes(b"collision")
    with pytest.raises(PostProcessError, match="already exists"):
        move_to_library(src, dest_dir, allow_already_moved=True)


def test_cleanup_target_file_and_directory(tmp_path: Path):
    movies_dir = tmp_path / "movies"
    movies_dir.mkdir()
    sibling = movies_dir / "Sibling (2020)"
    sibling.mkdir()
    (sibling / "movie.mkv").write_bytes(b"sibling")

    target_file = movies_dir / "BadFile.mkv"
    target_file.write_bytes(b"corrupted")
    cleanup_target(target_file)
    assert not target_file.exists()
    assert sibling.exists()

    target_dir = movies_dir / "BadDir (2024)"
    target_dir.mkdir()
    (target_dir / "bad.mkv").write_bytes(b"corrupted")
    cleanup_target(target_dir)
    assert not target_dir.exists()
    assert sibling.exists()


def test_run_subtitle_script_happy_path(tmp_path: Path):
    script = create_fake_script(
        tmp_path / "subs.py",
        """
import json, sys
summary = {
    "imdb_ok": 1,
    "imdb_fixed": [],
    "subs_downloaded": [],
    "subs_extracted": [],
    "subs_encoding_fixed": [],
    "subs_already_ok": 1,
    "subs_missing": [],
    "corrupted_videos": [],
    "skipped_items": [],
}
print("JSON_SUMMARY:" + json.dumps(summary))
sys.exit(0)
""",
    )
    movies_dir = tmp_path / "movies"
    movies_dir.mkdir()
    target = movies_dir / "movie.mkv"
    target.write_bytes(b"video")

    summary, warning = asyncio.run(
        run_subtitle_script(script, target, movies_dir, timeout_sec=10)
    )
    assert summary is not None
    assert summary["imdb_ok"] == 1
    assert warning is None


def test_run_subtitle_script_corrupted_raises(tmp_path: Path):
    script = create_fake_script(
        tmp_path / "subs_corrupt.py",
        """
import json, sys
summary = {
    "imdb_ok": 0,
    "imdb_fixed": [],
    "subs_downloaded": [],
    "subs_extracted": [],
    "subs_encoding_fixed": [],
    "subs_already_ok": 0,
    "subs_missing": [],
    "corrupted_videos": ["bad.mkv"],
    "skipped_items": [],
}
print("JSON_SUMMARY:" + json.dumps(summary))
sys.exit(0)
""",
    )
    movies_dir = tmp_path / "movies"
    movies_dir.mkdir()
    target = movies_dir / "bad.mkv"
    target.write_bytes(b"video")

    with pytest.raises(CorruptedVideoError, match="Corrupted video"):
        asyncio.run(run_subtitle_script(script, target, movies_dir, timeout_sec=10))


def test_run_subtitle_script_skipped_items_warning(tmp_path: Path):
    script = create_fake_script(
        tmp_path / "subs_skipped.py",
        """
import json, sys
summary = {
    "imdb_ok": 0,
    "imdb_fixed": [],
    "subs_downloaded": [],
    "subs_extracted": [],
    "subs_encoding_fixed": [],
    "subs_already_ok": 0,
    "subs_missing": [],
    "corrupted_videos": [],
    "skipped_items": ["extra.nfo"],
}
print("JSON_SUMMARY:" + json.dumps(summary))
sys.exit(0)
""",
    )
    movies_dir = tmp_path / "movies"
    movies_dir.mkdir()
    target = movies_dir / "movie.mkv"
    target.write_bytes(b"video")

    summary, warning = asyncio.run(
        run_subtitle_script(script, target, movies_dir, timeout_sec=10)
    )
    assert summary is not None
    assert warning is not None
    assert "extra.nfo" in warning


def test_run_subtitle_script_transient_error(tmp_path: Path):
    script = create_fake_script(
        tmp_path / "subs_crash.py",
        """
import sys
print("Network timeout querying IMDb", file=sys.stderr)
sys.exit(1)
""",
    )
    movies_dir = tmp_path / "movies"
    movies_dir.mkdir()
    target = movies_dir / "movie.mkv"
    target.write_bytes(b"video")

    summary, warning = asyncio.run(
        run_subtitle_script(script, target, movies_dir, timeout_sec=10)
    )
    assert summary is None
    assert warning is not None
    assert "Network timeout querying IMDb" in warning


def test_run_subtitle_script_timeout(tmp_path: Path):
    script = create_fake_script(
        tmp_path / "subs_hang.py",
        """
import time
time.sleep(10)
""",
    )
    movies_dir = tmp_path / "movies"
    movies_dir.mkdir()
    target = movies_dir / "movie.mkv"
    target.write_bytes(b"video")

    summary, warning = asyncio.run(
        run_subtitle_script(script, target, movies_dir, timeout_sec=1)
    )
    assert summary is None
    assert warning is not None
    assert "timed out" in warning


# ---------------------------------------------------------------------------
# Worker State Machine: 5 Critical Flows
# ---------------------------------------------------------------------------


def make_test_env(tmp_path: Path):
    dl_dir = tmp_path / "downloads"
    dl_movies = dl_dir / "complete" / "movies"
    dl_music = dl_dir / "complete" / "music"
    dl_movies.mkdir(parents=True)
    dl_music.mkdir(parents=True)

    movies_dir = tmp_path / "movies"
    music_dir = tmp_path / "music"
    movies_dir.mkdir()
    music_dir.mkdir()

    sub_script = create_fake_script(
        tmp_path / "fix_subtitles.py",
        """
import json, sys
summary = {
    "imdb_ok": 1,
    "imdb_fixed": [],
    "subs_downloaded": ["movie.pol.srt"],
    "subs_extracted": [],
    "subs_encoding_fixed": [],
    "subs_already_ok": 0,
    "subs_missing": [],
    "corrupted_videos": [],
    "skipped_items": [],
}
print("JSON_SUMMARY:" + json.dumps(summary))
sys.exit(0)
""",
    )

    db_path = tmp_path / "jobs.db"
    store = JobStore(db_path)
    store.init_schema()

    cfg = Settings(
        downloads_dir=dl_dir,
        movies_dir=movies_dir,
        music_dir=music_dir,
        subtitle_script=sub_script,
        db_path=db_path,
        jellyfin_db_path=tmp_path / "jellyfin_test_absent.db",
        notify_to="user@example.com",
        notify_from="bot@example.com",
    )
    return store, cfg, dl_movies, dl_music, movies_dir, music_dir, sub_script


def test_worker_flow1_movie_single_file_and_directory_happy_path(tmp_path: Path):
    """Flow 1: Single-file .mkv and directory Movie happy path."""
    store, cfg, dl_movies, _, movies_dir, _, _ = make_test_env(tmp_path)

    # 1a: Single-file movie
    file_src = dl_movies / "Inception (2010).mkv"
    file_src.write_bytes(b"inception-content")

    job1 = store.create_job(
        info_hash="aabbcc112233",
        name="Inception (2010)",
        category="movies",
        total_size=1000,
    )

    qb = FakeQBittorrentClient(
        {
            "aabbcc112233": TorrentProgress(
                info_hash="aabbcc112233",
                state="pausedUP",
                progress=1.0,
                dlspeed=0,
                eta=0,
                content_path="/downloads/complete/movies/Inception (2010).mkv",
                size=1000,
            )
        }
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))

        assert ("aabbcc112233", False) in qb.deleted_torrents
        expected_dest = movies_dir / "Inception (2010).mkv"
        assert expected_dest.is_file()
        assert not file_src.exists()

        updated_job = store.get_job(job1.id)
        assert updated_job is not None
        assert updated_job.state == "done"
        assert updated_job.dest_path == str(expected_dest)
        assert updated_job.subtitle_summary is not None
        assert "imdb_ok" in updated_job.subtitle_summary
        assert updated_job.error is None

        mock_email.assert_called_once()
        subject, body = mock_email.call_args[0][1], mock_email.call_args[0][2]
        assert "Pobrano: Inception (2010)" in subject
        assert "Inception (2010)" in body
        assert str(expected_dest) in body
        assert "Otwórz w Jellyfin" in (mock_email.call_args.kwargs.get("html_body") or "")

    # 1b: Directory movie
    dir_src = dl_movies / "Dune Part Two (2024)"
    dir_src.mkdir()
    (dir_src / "dune.mkv").write_bytes(b"dune-content")

    job2 = store.create_job(
        info_hash="ddeeff445566",
        name="Dune Part Two (2024)",
        category="movies",
        total_size=5000,
    )
    # Set to stoppedUP (qBittorrent v5 status)
    qb.torrents["ddeeff445566"] = TorrentProgress(
        info_hash="ddeeff445566",
        state="stoppedUP",
        progress=1.0,
        dlspeed=0,
        eta=0,
        content_path="/downloads/complete/movies/Dune Part Two (2024)",
        size=5000,
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))

        assert ("ddeeff445566", False) in qb.deleted_torrents
        expected_dir = movies_dir / "Dune Part Two (2024)"
        assert expected_dir.is_dir()
        assert (expected_dir / "dune.mkv").is_file()
        assert not dir_src.exists()

        updated_job2 = store.get_job(job2.id)
        assert updated_job2 is not None
        assert updated_job2.state == "done"
        mock_email.assert_called_once()


def test_worker_flow2_music_happy_path(tmp_path: Path):
    """Flow 2: Music happy path: moved to music_dir, subtitle script NOT called, state == 'done'."""
    store, cfg, _, dl_music, _, music_dir, sub_script = make_test_env(tmp_path)

    album_src = dl_music / "Pink Floyd - Dark Side (1973)"
    album_src.mkdir()
    (album_src / "01-speak.flac").write_bytes(b"audio")

    job = store.create_job(
        info_hash="112233445566",
        name="Pink Floyd - Dark Side (1973)",
        category="music",
        total_size=3000,
    )

    qb = FakeQBittorrentClient(
        {
            "112233445566": TorrentProgress(
                info_hash="112233445566",
                state="uploading",
                progress=1.0,
                dlspeed=0,
                eta=0,
                content_path="/downloads/complete/music/Pink Floyd - Dark Side (1973)",
                size=3000,
            )
        }
    )

    with mock.patch("worker.run_subtitle_script") as mock_sub:
        with mock.patch("worker.send_email") as mock_email:
            asyncio.run(poll_once(store, qb, cfg))

            mock_sub.assert_not_called()
            expected_music = music_dir / "Pink Floyd - Dark Side (1973)"
            assert expected_music.is_dir()
            assert (expected_music / "01-speak.flac").is_file()
            assert not album_src.exists()

            updated_job = store.get_job(job.id)
            assert updated_job is not None
            assert updated_job.state == "done"
            assert updated_job.dest_path == str(expected_music)
            assert updated_job.subtitle_summary is None

            mock_email.assert_called_once()
            subject, body = mock_email.call_args[0][1], mock_email.call_args[0][2]
            assert "Pobrano muzykę: Pink Floyd - Dark Side (1973)" in subject
            assert "NapiProjekt" not in body


def test_worker_crash_recovery_resuming_moving_state_already_moved(tmp_path: Path):
    """Crash recovery: job interrupted in 'moving' state with payload already at dest recovers cleanly."""
    store, cfg, dl_movies, _, movies_dir, _, sub_script = make_test_env(tmp_path)

    # Payload already in movies_dir (shutil.move finished before restart crash)
    dest_movie_dir = movies_dir / "Interrupted Movie (2024)"
    dest_movie_dir.mkdir()
    (dest_movie_dir / "movie.mkv").write_bytes(b"recovered-movie-data")

    # Source does NOT exist in dl_movies
    assert not (dl_movies / "Interrupted Movie (2024)").exists()

    # Job is in 'moving' state in SQLite (crash happened before 'post_processing' commit)
    job = store.create_job(
        info_hash="deadbeef11223344",
        name="Interrupted Movie (2024)",
        category="movies",
        total_size=5000,
    )
    store.update_job(
        job.id,
        state="moving",
        content_path="/downloads/complete/movies/Interrupted Movie (2024)",
    )

    qb = FakeQBittorrentClient()

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))

        updated_job = store.get_job(job.id)
        assert updated_job is not None
        assert updated_job.state == "done"
        assert updated_job.dest_path == str(dest_movie_dir)
        mock_email.assert_called_once()
        assert "Pobrano: Interrupted Movie (2024)" in mock_email.call_args[0][1]


def test_worker_flow3_destination_collision(tmp_path: Path):
    """Flow 3: Destination collision: existing folder/file in movies_dir is NOT overwritten."""
    store, cfg, dl_movies, _, movies_dir, _, _ = make_test_env(tmp_path)

    # Existing movie in movies_dir
    existing = movies_dir / "Existing Movie (2020)"
    existing.mkdir()
    (existing / "existing.mkv").write_bytes(b"original")

    # Staging copy in downloads
    staging = dl_movies / "Existing Movie (2020)"
    staging.mkdir()
    (staging / "new.mkv").write_bytes(b"new-content")

    job = store.create_job(
        info_hash="ccddeeff0011",
        name="Existing Movie (2020)",
        category="movies",
        total_size=2000,
    )

    qb = FakeQBittorrentClient(
        {
            "ccddeeff0011": TorrentProgress(
                info_hash="ccddeeff0011",
                state="pausedUP",
                progress=1.0,
                dlspeed=0,
                eta=0,
                content_path="/downloads/complete/movies/Existing Movie (2020)",
                size=2000,
            )
        }
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))

        # Destination collision should leave staging copy intact!
        assert staging.is_dir()
        assert (staging / "new.mkv").read_bytes() == b"new-content"
        # Existing copy untouched
        assert (existing / "existing.mkv").read_bytes() == b"original"

        updated = store.get_job(job.id)
        assert updated is not None
        assert updated.state == "failed"
        assert updated.error is not None
        assert "already exists" in updated.error

        mock_email.assert_called_once()
        subject, body = mock_email.call_args[0][1], mock_email.call_args[0][2]
        assert "Błąd: Existing Movie (2020)" in subject
        assert "already exists" in body


def test_worker_flow4_corrupted_video_cleanup(tmp_path: Path):
    """Flow 4: Corrupted video reported by subtitle script: moved file/dir is deleted, sibling movies untouched."""
    store, cfg, dl_movies, _, movies_dir, _, _ = make_test_env(tmp_path)

    # Sibling movie in movies_dir
    sibling = movies_dir / "Good Sibling Movie (2021)"
    sibling.mkdir()
    (sibling / "good.mkv").write_bytes(b"good")

    # Corrupted movie staging
    staging = dl_movies / "Corrupted Movie (2024)"
    staging.mkdir()
    (staging / "corrupted.mkv").write_bytes(b"bad")

    corrupt_script = create_fake_script(
        tmp_path / "corrupt_sub.py",
        """
import json, sys
summary = {
    "imdb_ok": 0,
    "imdb_fixed": [],
    "subs_downloaded": [],
    "subs_extracted": [],
    "subs_encoding_fixed": [],
    "subs_already_ok": 0,
    "subs_missing": [],
    "corrupted_videos": ["corrupted.mkv"],
    "skipped_items": [],
}
print("JSON_SUMMARY:" + json.dumps(summary))
sys.exit(0)
""",
    )
    cfg.subtitle_script = corrupt_script

    job = store.create_job(
        info_hash="bad0bad0bad0",
        name="Corrupted Movie (2024)",
        category="movies",
        total_size=4000,
    )

    qb = FakeQBittorrentClient(
        {
            "bad0bad0bad0": TorrentProgress(
                info_hash="bad0bad0bad0",
                state="pausedUP",
                progress=1.0,
                dlspeed=0,
                eta=0,
                content_path="/downloads/complete/movies/Corrupted Movie (2024)",
                size=4000,
            )
        }
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))

        # Target should be deleted from movies_dir!
        assert not (movies_dir / "Corrupted Movie (2024)").exists()
        # Sibling movie must be untouched!
        assert (sibling / "good.mkv").is_file()

        updated = store.get_job(job.id)
        assert updated is not None
        assert updated.state == "failed"
        assert updated.error is not None
        assert "corrupted.mkv" in updated.error

        mock_email.assert_called_once()
        subject, body = mock_email.call_args[0][1], mock_email.call_args[0][2]
        assert "Błąd: Corrupted Movie (2024)" in subject
        assert "corrupted.mkv" in body


def test_worker_flow5_transient_script_crash_warning(tmp_path: Path):
    """Flow 5: Transient subtitle script crash without corrupted_videos: movie stays, state == 'done' with warning."""
    store, cfg, dl_movies, _, movies_dir, _, _ = make_test_env(tmp_path)

    crash_script = create_fake_script(
        tmp_path / "crash_sub.py",
        """
import sys
print("Simulated crash: Subtitle API 500 Server Error", file=sys.stderr)
sys.exit(2)
""",
    )
    cfg.subtitle_script = crash_script

    file_src = dl_movies / "Gladiator (2000).mkv"
    file_src.write_bytes(b"gladiator")

    job = store.create_job(
        info_hash="1234gladiator",
        name="Gladiator (2000)",
        category="movies",
        total_size=1500,
    )

    qb = FakeQBittorrentClient(
        {
            "1234gladiator": TorrentProgress(
                info_hash="1234gladiator",
                state="pausedUP",
                progress=1.0,
                dlspeed=0,
                eta=0,
                content_path="/downloads/complete/movies/Gladiator (2000).mkv",
                size=1500,
            )
        }
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))

        # Movie stays in movies_dir!
        moved_file = movies_dir / "Gladiator (2000).mkv"
        assert moved_file.is_file()

        updated = store.get_job(job.id)
        assert updated is not None
        assert updated.state == "done"
        assert updated.warning is not None
        assert "Subtitle API 500" in updated.warning
        assert updated.error is None

        mock_email.assert_called_once()
        subject, body = mock_email.call_args[0][1], mock_email.call_args[0][2]
        assert "Pobrano (z uwagą): Gladiator (2000)" in subject
        assert "Subtitle API 500" in body


def test_worker_downloading_progress_update(tmp_path: Path):
    """Torrent still downloading updates progress, dlspeed, eta in DB without moving or emailing."""
    store, cfg, _, _, _, _, _ = make_test_env(tmp_path)

    job = store.create_job(
        info_hash="progress1234",
        name="In Progress",
        category="movies",
        total_size=10000,
    )

    qb = FakeQBittorrentClient(
        {
            "progress1234": TorrentProgress(
                info_hash="progress1234",
                state="downloading",
                progress=0.45,
                dlspeed=204800,
                eta=120,
                content_path="/downloads/complete/movies/In Progress.mkv",
                size=10000,
            )
        }
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))

        mock_email.assert_not_called()
        assert len(qb.deleted_torrents) == 0

        updated = store.get_job(job.id)
        assert updated is not None
        assert updated.state == "downloading"
        assert updated.progress == 0.45
        assert updated.dlspeed == 204800
        assert updated.eta == 120
        assert updated.content_path == "/downloads/complete/movies/In Progress.mkv"


def test_worker_loop_clean_stop(tmp_path: Path):
    """Worker loop runs and stops cleanly when stop_event is set."""
    store, cfg, _, _, _, _, _ = make_test_env(tmp_path)
    qb = FakeQBittorrentClient()

    stop_event = asyncio.Event()

    async def run_and_stop():
        task = asyncio.create_task(run_worker_loop(store, qb, cfg, stop_event, interval_sec=0.05))
        await asyncio.sleep(0.1)
        stop_event.set()
        await task

    asyncio.run(run_and_stop())


def test_worker_magnet_metadata_sync_while_downloading(tmp_path: Path):
    """Magnet job with total_size=0 gets real name and total_size once metadata arrives."""
    store, cfg, _, _, _, _, _ = make_test_env(tmp_path)
    job = store.create_job(
        info_hash="abcd" * 10,
        name="magnet-abcdabcdabcd",
        category="movies",
        total_size=0,
    )

    qb = FakeQBittorrentClient(
        {
            "abcd" * 10: TorrentProgress(
                info_hash="abcd" * 10,
                state="downloading",
                progress=0.15,
                dlspeed=500000,
                eta=60,
                content_path="/downloads/complete/movies/Inception (2010)",
                size=1500000,
                name="Inception (2010)",
            )
        }
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))
        mock_email.assert_not_called()

    updated = store.get_job(job.id)
    assert updated is not None
    assert updated.state == "downloading"
    assert updated.name == "Inception (2010)"
    assert updated.total_size == 1500000
    assert updated.progress == 0.15


def test_worker_magnet_single_poll_completion_syncs_name_and_size(tmp_path: Path):
    """Magnet resolving and finishing in one poll updates name/total_size before completion email."""
    store, cfg, dl_movies, _, movies_dir, _, _ = make_test_env(tmp_path)
    movie_file = dl_movies / "Arrival (2016).mkv"
    movie_file.write_bytes(b"video-bytes")

    job = store.create_job(
        info_hash="1234" * 10,
        name="magnet-123412341234",
        category="movies",
        total_size=0,
    )

    qb = FakeQBittorrentClient(
        {
            "1234" * 10: TorrentProgress(
                info_hash="1234" * 10,
                state="pausedUP",
                progress=1.0,
                dlspeed=0,
                eta=0,
                content_path="/downloads/complete/movies/Arrival (2016).mkv",
                size=4096,
                name="Arrival (2016)",
            )
        }
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))

        assert (movies_dir / "Arrival (2016).mkv").is_file()
        updated = store.get_job(job.id)
        assert updated is not None
        assert updated.state == "done"
        assert updated.name == "Arrival (2016)"
        assert updated.total_size == 4096

        mock_email.assert_called_once()
        subject, body = mock_email.call_args[0][1], mock_email.call_args[0][2]
        assert "Arrival (2016)" in subject
        assert "4,096 bajtów" in body


def test_worker_magnet_metadata_timeout_fails_and_cleans_up(tmp_path: Path):
    """Dead magnet stuck in metaDL past timeout is deleted from qB, marked failed, and emailed."""
    from datetime import datetime, timedelta, timezone
    import sqlite3

    store, cfg, _, _, _, _, _ = make_test_env(tmp_path)
    cfg.magnet_metadata_timeout_sec = 900

    job = store.create_job(
        info_hash="dead" * 10,
        name="Dead Magnet",
        category="music",
        total_size=0,
    )
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=905)).isoformat()
    with sqlite3.connect(str(cfg.db_path)) as conn:
        conn.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (old_ts, job.id))
        conn.commit()

    qb = FakeQBittorrentClient(
        {
            "dead" * 10: TorrentProgress(
                info_hash="dead" * 10,
                state="metaDL",
                progress=0.0,
                dlspeed=0,
                eta=8640000,
                content_path="",
                size=0,
                name="Dead Magnet",
            )
        }
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))

        assert qb.deleted_torrents == [("dead" * 10, True)]
        updated = store.get_job(job.id)
        assert updated is not None
        assert updated.state == "failed"
        assert "Timed out waiting for magnet metadata" in (updated.error or "")

        mock_email.assert_called_once()
        subject, body = mock_email.call_args[0][1], mock_email.call_args[0][2]
        assert "Błąd: Dead Magnet" in subject
        assert "Timed out waiting for magnet metadata" in body


def test_worker_no_false_positive_metadata_timeout(tmp_path: Path):
    """Regular .torrent (total_size > 0), fresh metaDL magnet, and timeout<=0 do not time out."""
    from datetime import datetime, timedelta, timezone
    import sqlite3

    store, cfg, _, _, _, _, _ = make_test_env(tmp_path)
    cfg.magnet_metadata_timeout_sec = 900

    fresh_magnet = store.create_job(info_hash="f00d" * 10, name="Fresh Magnet", category="movies", total_size=0)
    old_torrent = store.create_job(info_hash="beef" * 10, name="Stalled Torrent", category="movies", total_size=50000)

    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=3600)).isoformat()
    with sqlite3.connect(str(cfg.db_path)) as conn:
        conn.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (old_ts, old_torrent.id))
        conn.commit()

    qb = FakeQBittorrentClient(
        {
            "f00d" * 10: TorrentProgress(
                info_hash="f00d" * 10,
                state="metaDL",
                progress=0.0,
                dlspeed=0,
                eta=8640000,
                content_path="",
                size=0,
                name="Fresh Magnet",
            ),
            "beef" * 10: TorrentProgress(
                info_hash="beef" * 10,
                state="stalledDL",
                progress=0.2,
                dlspeed=0,
                eta=8640000,
                content_path="",
                size=50000,
                name="Stalled Torrent",
            ),
        }
    )

    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))
        mock_email.assert_not_called()
        assert qb.deleted_torrents == []
        assert store.get_job(fresh_magnet.id).state == "downloading"
        assert store.get_job(old_torrent.id).state == "downloading"

    # Disabling timeout with 0 prevents timeout even on aged metaDL magnet
    with sqlite3.connect(str(cfg.db_path)) as conn:
        conn.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (old_ts, fresh_magnet.id))
        conn.commit()
    cfg.magnet_metadata_timeout_sec = 0
    with mock.patch("worker.send_email") as mock_email:
        asyncio.run(poll_once(store, qb, cfg))
        mock_email.assert_not_called()
        assert store.get_job(fresh_magnet.id).state == "downloading"


def test_worker_loop_nonblocking_notification_and_poster_order(tmp_path: Path):
    """Slow Jellyfin indexing notification runs in background without stalling other torrents."""
    import time as _time

    store, cfg, dl_movies, _, movies_dir, _, _ = make_test_env(tmp_path)

    src_dir = dl_movies / "Dune.2021"
    src_dir.mkdir()
    (src_dir / "Dune.2021.mkv").write_bytes(b"video-data")

    done_job = store.create_job(info_hash="dune" * 10, name="Dune (2021)", category="movies", total_size=1000)
    active_job = store.create_job(info_hash="red1" * 10, name="Red Dragon", category="movies", total_size=2000)

    qb = FakeQBittorrentClient(
        {
            "dune" * 10: TorrentProgress(
                info_hash="dune" * 10,
                state="pausedUP",
                progress=1.0,
                dlspeed=0,
                eta=0,
                content_path="/downloads/complete/movies/Dune.2021",
                size=1000,
            ),
            "red1" * 10: TorrentProgress(
                info_hash="red1" * 10,
                state="downloading",
                progress=0.25,
                dlspeed=100000,
                eta=30,
                content_path="/downloads/complete/movies/Red.Dragon",
                size=2000,
            ),
        }
    )

    fake_jpeg = b"\xff\xd8\xff\xe0" + (b"\x00" * 16)
    expected_url = "https://jellyfin.marzeta.pl/web/#/details?id=abc123&serverId=srv1"
    poll_ticks_during_notify: list[float] = []

    def slow_resolve_url(job, _cfg):
        # Simulate Jellyfin indexing completing asynchronously and writing folder.jpg
        _time.sleep(0.15)
        (movies_dir / "Dune.2021" / "folder.jpg").write_bytes(fake_jpeg)
        return expected_url

    original_get_torrents = qb.get_torrents

    async def tracked_get_torrents(hashes: list[str]):
        poll_ticks_during_notify.append(_time.monotonic())
        qb.torrents["red1" * 10] = TorrentProgress(
            info_hash="red1" * 10,
            state="downloading",
            progress=0.55,
            dlspeed=150000,
            eta=15,
            content_path="/downloads/complete/movies/Red.Dragon",
            size=2000,
        )
        return await original_get_torrents(hashes)

    stop_event = asyncio.Event()

    async def run_scenario():
        loop_task = asyncio.create_task(run_worker_loop(store, qb, cfg, stop_event, interval_sec=0.02))
        # Wait until background email fires (poll loop keeps polling active_job meanwhile)
        deadline = _time.monotonic() + 3.0
        while mock_email.call_count == 0 and _time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        stop_event.set()
        await loop_task

    with (
        mock.patch.object(qb, "get_torrents", side_effect=tracked_get_torrents),
        mock.patch("worker.resolve_jellyfin_item_url", side_effect=slow_resolve_url),
        mock.patch("worker.send_email") as mock_email,
    ):
        asyncio.run(run_scenario())

        # While slow_resolve_url slept 0.15s, multiple 0.02s poll cycles still ran for Red Dragon
        assert len(poll_ticks_during_notify) >= 3
        assert store.get_job(done_job.id).state == "done"
        assert store.get_job(active_job.id).progress == 0.55

        import html as _html

        mock_email.assert_called_once()
        kwargs = mock_email.call_args.kwargs
        body = mock_email.call_args[0][2]
        assert expected_url in body
        assert _html.escape(expected_url, quote=True) in kwargs["html_body"]
        assert kwargs["inline_images"] == {"poster": (fake_jpeg, "jpeg")}
