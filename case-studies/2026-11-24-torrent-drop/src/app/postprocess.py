from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import sys
from typing import Any


class PostProcessError(RuntimeError):
    """Base exception for post-processing errors."""
    pass


class CorruptedVideoError(PostProcessError):
    """Raised when the subtitle script reports corrupted videos."""
    pass


def map_container_path(content_path: str, downloads_dir: Path) -> Path:
    """Map a container download path (e.g. /downloads/complete/...) to a host path safely."""
    if not content_path.startswith("/downloads/"):
        raise PostProcessError(f"Content path '{content_path}' does not start with '/downloads/'")

    rel_str = content_path[len("/downloads/"):].lstrip("/")
    if not rel_str:
        raise PostProcessError(f"Content path '{content_path}' resolves to downloads root")

    base = downloads_dir.resolve()
    target = (base / rel_str).resolve()

    try:
        target.relative_to(base)
    except ValueError:
        raise PostProcessError(f"Path traversal detected in content path '{content_path}'")

    if target == base:
        raise PostProcessError(f"Content path '{content_path}' resolves to downloads root")

    return target


def move_to_library(src_path: Path, dest_dir: Path, allow_already_moved: bool = False) -> Path:
    """Move downloaded file or directory into destination library directory."""
    dest = dest_dir / src_path.name

    if not src_path.exists():
        if allow_already_moved and dest.exists():
            return dest
        raise PostProcessError(f"Source path '{src_path}' does not exist")

    if dest.exists():
        raise PostProcessError(f"Destination path '{dest}' already exists")

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_path), str(dest))
    return dest


def cleanup_target(path: Path) -> None:
    """Safely delete target file or directory without affecting sibling items."""
    try:
        resolved = path.resolve()
    except OSError:
        return

    if resolved == Path("/") or resolved == Path.home() or not path.name:
        raise PostProcessError(f"Refusing to delete unsafe target path: {path}")

    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


async def run_subtitle_script(
    script_path: Path,
    target_path: Path,
    movies_dir: Path,
    timeout_sec: int = 300,
) -> tuple[dict[str, Any] | None, str | None]:
    """Execute the movie subtitle / IMDb script against target_path."""
    cmd = [
        sys.executable,
        str(script_path),
        "--movies-dir",
        str(movies_dir),
        "--target",
        str(target_path),
        "--json-summary",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return None, f"Failed to execute subtitle script: {exc}"

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except OSError:
            pass
        return None, f"Subtitle script timed out after {timeout_sec}s"

    stdout_text = stdout_b.decode("utf-8", errors="replace")
    stderr_text = stderr_b.decode("utf-8", errors="replace")

    summary: dict[str, Any] | None = None
    for line in stdout_text.splitlines():
        if line.startswith("JSON_SUMMARY:"):
            try:
                summary = json.loads(line.removeprefix("JSON_SUMMARY:"))
            except Exception:
                summary = None
            break

    # Surface corrupted videos as fatal CorruptedVideoError
    if summary and summary.get("corrupted_videos"):
        raise CorruptedVideoError(
            f"Corrupted video(s) detected: {summary['corrupted_videos']}"
        )

    # Check non-zero exit
    if proc.returncode != 0:
        detail = stderr_text.strip() or stdout_text.strip() or f"exit code {proc.returncode}"
        warning = f"Subtitle script failed (exit code {proc.returncode}): {detail}"
        return summary, warning

    # Check skipped_items warning
    warning = None
    if summary and summary.get("skipped_items"):
        warning = f"Subtitle script reported skipped items: {summary['skipped_items']}"

    return summary, warning
