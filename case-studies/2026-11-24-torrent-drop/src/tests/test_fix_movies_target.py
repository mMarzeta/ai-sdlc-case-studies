import json
from pathlib import Path
import subprocess
import sys
from unittest import mock
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "jellyfin"))
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
            sys.executable,
            str(REPO_ROOT / "jellyfin" / "fix_movies_subtitles_imdb.py"),
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


def test_cli_target_outside_movies_dir_fails(tmp_path: Path):
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    outside_dir = tmp_path / "Outside"
    outside_dir.mkdir()

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "jellyfin" / "fix_movies_subtitles_imdb.py"),
            "--movies-dir",
            str(movies_dir),
            "--target",
            str(outside_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "outside movies dir" in proc.stderr


def test_cli_target_missing_fails(tmp_path: Path):
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    missing_target = movies_dir / "NonExistentMovie (2020)"

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "jellyfin" / "fix_movies_subtitles_imdb.py"),
            "--movies-dir",
            str(movies_dir),
            "--target",
            str(missing_target),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "does not exist" in proc.stderr


def test_docker_daemon_down_raises_runtime_error_not_corrupted(tmp_path: Path):
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    target_dir = movies_dir / "Gladiator (2000)"
    target_dir.mkdir()
    vid = target_dir / "Gladiator.2000.mkv"
    vid.write_bytes(b"gladiator-content")

    summary = fms.Summary()
    item = fms.MovieItem(
        folder=target_dir,
        video_path=vid,
        nfo_paths=[],
        is_root_file=False,
        clean_title="Gladiator",
        parsed_year=2000,
    )

    fake_docker_err = subprocess.CompletedProcess(
        args=["docker", "exec"],
        returncode=125,
        stdout="",
        stderr="Error response from daemon: Container jellyfin is not running",
    )

    with mock.patch("subprocess.run", return_value=fake_docker_err):
        # probe_video directly raises RuntimeError
        with pytest.raises(RuntimeError, match="Container jellyfin is not running"):
            fms.probe_video(vid, movies_dir=movies_dir)

        # process_movie propagates RuntimeError without adding to corrupted_videos
        with pytest.raises(RuntimeError, match="Container jellyfin is not running"):
            fms.process_movie(item, dry_run=False, summary=summary, movies_dir=movies_dir)

        assert summary.corrupted_videos == []

    # Verify main() exits non-zero cleanly without printing corrupted_videos
    test_args = [
        "fix_movies_subtitles_imdb.py",
        "--movies-dir",
        str(movies_dir),
        "--target",
        str(target_dir),
        "--json-summary",
    ]
    with mock.patch.object(sys, "argv", test_args):
        with mock.patch("subprocess.run", return_value=fake_docker_err):
            exit_code = fms.main()
            assert exit_code != 0


def test_genuine_ffprobe_failure_marks_corrupted_video(tmp_path: Path):
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    target_dir = movies_dir / "Broken (2020)"
    target_dir.mkdir()
    vid = target_dir / "Broken.2020.mkv"
    vid.write_bytes(b"broken-content")

    summary = fms.Summary()
    item = fms.MovieItem(
        folder=target_dir,
        video_path=vid,
        nfo_paths=[],
        is_root_file=False,
        clean_title="Broken",
        parsed_year=2020,
    )

    fake_ffprobe_err = subprocess.CompletedProcess(
        args=["docker", "exec"],
        returncode=1,
        stdout="",
        stderr="[matroska,webm @ 0x5555] Invalid data found when processing input",
    )

    with mock.patch("subprocess.run", return_value=fake_ffprobe_err):
        healthy, fps, subs, err = fms.probe_video(vid, movies_dir=movies_dir)
        assert healthy is False
        assert "Invalid data found" in err

        fms.process_movie(item, dry_run=False, summary=summary, movies_dir=movies_dir)
        assert len(summary.corrupted_videos) == 1
        assert "Broken.2020.mkv" in summary.corrupted_videos[0]


def test_fix_imdb_in_nfo_records_movie_meta(tmp_path: Path):
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    target_dir = movies_dir / "Lost.In.Translation.2003"
    target_dir.mkdir()
    vid = target_dir / "Lost.In.Translation.2003.mkv"
    vid.write_bytes(b"vid")

    item = fms.MovieItem(
        folder=target_dir,
        video_path=vid,
        nfo_paths=[],
        is_root_file=False,
        clean_title="Lost In Translation",
        parsed_year=2003,
    )
    fake_hit = {
        "id": "tt0335266",
        "l": "Lost in Translation",
        "y": 2003,
        "s": "Bill Murray, Scarlett Johansson",
        "i": {"imageUrl": "https://m.media-amazon.com/images/M/test._V1_.jpg"},
    }

    summary = fms.Summary()
    with mock.patch.object(fms, "imdb_search_movie", return_value=fake_hit):
        fms.fix_imdb_in_nfo(item, dry_run=True, summary=summary)

    assert summary.movie_meta == {
        "imdb_id": "tt0335266",
        "title": "Lost in Translation",
        "year": 2003,
        "actors": "Bill Murray, Scarlett Johansson",
        "poster_url": "https://m.media-amazon.com/images/M/test._V1_.jpg",
    }

    # Also records when NFO already has valid IMDb ID
    nfo = target_dir / "movie.nfo"
    nfo.write_text("<movie><imdbid>tt0335266</imdbid><title>Lost in Translation</title><year>2003</year></movie>", encoding="utf-8")
    item_with_nfo = fms.MovieItem(
        folder=target_dir,
        video_path=vid,
        nfo_paths=[nfo],
        is_root_file=False,
        clean_title="Lost In Translation",
        parsed_year=2003,
    )
    summary_ok = fms.Summary()
    with mock.patch.object(fms, "imdb_lookup_id", return_value=fake_hit):
        fms.fix_imdb_in_nfo(item_with_nfo, dry_run=True, summary=summary_ok)

    assert summary_ok.imdb_ok == 1
    assert summary_ok.movie_meta == {
        "imdb_id": "tt0335266",
        "title": "Lost in Translation",
        "year": 2003,
        "actors": "Bill Murray, Scarlett Johansson",
        "poster_url": "https://m.media-amazon.com/images/M/test._V1_.jpg",
    }


