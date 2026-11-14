from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import Settings
from db import JobRecord, JobStore
from notifier import (
    format_completion_email,
    format_completion_html,
    format_failure_email,
    format_failure_html,
    resolve_jellyfin_item_url,
    resolve_poster_image,
    send_email,
)
from postprocess import (
    CorruptedVideoError,
    PostProcessError,
    cleanup_target,
    map_container_path,
    move_to_library,
    run_subtitle_script,
)
from torrent_client import QBittorrentClient, QBittorrentError

logger = logging.getLogger(__name__)

COMPLETED_QB_STATES = {
    "pausedUP",
    "stoppedUP",
    "uploading",
    "stalledUP",
    "queuedUP",
    "forcedUP",
}


async def _send_completion_notification(
    job: JobRecord,
    cfg: Settings,
    summary: dict[str, Any] | None,
    warning: str | None,
) -> None:
    """Wait for Jellyfin indexing if needed, resolve poster, and send completion email."""
    try:
        # Resolve the Jellyfin item URL first so Jellyfin's library scan finishes
        # (and writes folder.jpg) before we pick the poster image.
        jellyfin_item_url = await asyncio.to_thread(resolve_jellyfin_item_url, job, cfg)
        poster = await asyncio.to_thread(resolve_poster_image, job, summary)
        subject, body = format_completion_email(
            job,
            subtitle_summary=summary,
            warning=warning,
            cfg=cfg,
            jellyfin_item_url=jellyfin_item_url,
        )
        html_body = format_completion_html(
            job,
            subtitle_summary=summary,
            warning=warning,
            cfg=cfg,
            has_poster=poster is not None,
            jellyfin_item_url=jellyfin_item_url,
        )
        inline_images = {"poster": poster} if poster is not None else None
        await asyncio.to_thread(
            send_email,
            cfg,
            subject,
            body,
            html_body=html_body,
            inline_images=inline_images,
        )
    except Exception as email_err:
        logger.exception("Failed to send completion email for job %d: %s", job.id, email_err)


async def _dispatch_notification(
    coro: Coroutine[Any, Any, None],
    background_tasks: set[asyncio.Task[Any]] | None,
) -> None:
    """Run notification in background when a task registry is active, else await inline."""
    if background_tasks is None:
        await coro
        return
    task = asyncio.create_task(coro)
    background_tasks.add(task)

    def _on_done(done_task: asyncio.Task[Any]) -> None:
        background_tasks.discard(done_task)
        if not done_task.cancelled():
            exc = done_task.exception()
            if exc is not None:
                logger.exception("Unhandled error in background notification task", exc_info=exc)

    task.add_done_callback(_on_done)


async def _send_failure_notification(job: JobRecord, cfg: Settings) -> None:
    """Send rich HTML + plain-text failure email for a failed job."""
    try:
        subject, body = format_failure_email(job, cfg=cfg)
        html_body = format_failure_html(job, cfg=cfg)
        await asyncio.to_thread(send_email, cfg, subject, body, html_body=html_body)
    except Exception as email_err:
        logger.exception("Failed to send failure email for job %d: %s", job.id, email_err)


async def _handle_completion(
    job: JobRecord,
    content_path: str | None,
    store: JobStore,
    qb: QBittorrentClient,
    cfg: Settings,
    background_tasks: set[asyncio.Task[Any]] | None = None,
) -> None:
    dest_path: Path | None = Path(job.dest_path) if job.dest_path else None
    try:
        # Step 1: Mark completed_in_client and remove from client without deleting files
        if job.state in ("submitted", "downloading"):
            job = store.update_job(
                job.id,
                state="completed_in_client",
                progress=1.0,
                dlspeed=0,
                eta=0,
                content_path=content_path,
            )
            try:
                await qb.delete_torrent(job.info_hash, delete_files=False)
            except QBittorrentError as exc:
                logger.warning("Error deleting torrent %s from client: %s", job.info_hash, exc)

        # Step 2: Move files
        allow_already_moved = (job.state == "moving")
        if job.state == "completed_in_client":
            job = store.update_job(job.id, state="moving")

        if job.state == "moving":
            effective_content_path = job.content_path or content_path
            if not effective_content_path:
                raise PostProcessError(f"Missing content_path for job {job.name} (id={job.id})")

            src_path = map_container_path(effective_content_path, cfg.downloads_dir)

            cat = (job.category or "").strip().lower()
            if cat in ("movies", "movie"):
                dest_dir = cfg.movies_dir
            elif cat in ("music",):
                dest_dir = cfg.music_dir
            else:
                raise PostProcessError(f"Unsupported category '{job.category}' for job {job.name}")

            dest_path = move_to_library(src_path, dest_dir, allow_already_moved=allow_already_moved)
            job = store.update_job(job.id, dest_path=str(dest_path), state="post_processing")

        # Step 3: Post-processing (subtitles/IMDb for movies)
        summary: dict[str, Any] | None = None
        warning: str | None = None

        if job.state == "post_processing":
            target = Path(job.dest_path) if job.dest_path else dest_path
            if not target:
                raise PostProcessError(f"Missing dest_path for post-processing job {job.name}")

            cat = (job.category or "").strip().lower()
            if cat in ("movies", "movie"):
                summary, warning = await run_subtitle_script(
                    cfg.subtitle_script,
                    target,
                    cfg.movies_dir,
                )

            # Step 4: Mark done in DB
            sub_json = json.dumps(summary) if summary is not None else None
            job = store.update_job(
                job.id,
                state="done",
                dest_path=str(target),
                subtitle_summary=sub_json,
                warning=warning,
            )

            # Step 5: Send completion email (backgrounded in run_worker_loop so other downloads keep polling)
            await _dispatch_notification(
                _send_completion_notification(job, cfg, summary, warning),
                background_tasks,
            )

    except CorruptedVideoError as exc:
        logger.error("Job %d (%s) failed due to corrupted video: %s", job.id, job.name, exc)
        target_to_clean = Path(job.dest_path) if job.dest_path else dest_path
        if target_to_clean:
            try:
                cleanup_target(target_to_clean)
            except Exception as clean_err:
                logger.error("Failed to cleanup corrupted target %s: %s", target_to_clean, clean_err)

        job = store.update_job(job.id, state="failed", error=str(exc))
        await _send_failure_notification(job, cfg)

    except Exception as exc:
        logger.error("Job %d (%s) failed: %s", job.id, job.name, exc)
        job = store.update_job(job.id, state="failed", error=str(exc))
        await _send_failure_notification(job, cfg)


METADATA_QB_STATES = {"metaDL", "forcedMetaDL"}


def _is_metadata_timed_out(job: JobRecord, timeout_sec: int) -> bool:
    """Return True if a job waiting on magnet metadata has exceeded timeout_sec."""
    if timeout_sec <= 0 or not job.created_at:
        return False
    try:
        created = datetime.fromisoformat(job.created_at)
    except ValueError:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).total_seconds() >= timeout_sec


async def _fail_metadata_timeout(
    job: JobRecord,
    store: JobStore,
    qb: QBittorrentClient,
    cfg: Settings,
) -> None:
    """Delete timed-out magnet from qBittorrent, mark job failed, and notify."""
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
    await _send_failure_notification(failed_job, cfg)


async def _process_job(
    job: JobRecord,
    torrents_dict: dict[str, Any],
    store: JobStore,
    qb: QBittorrentClient,
    cfg: Settings,
    background_tasks: set[asyncio.Task[Any]] | None = None,
) -> None:
    if job.state in ("submitted", "downloading"):
        prog = torrents_dict.get(job.info_hash.lower()) or torrents_dict.get(job.info_hash)
        if not prog:
            return

        waiting_metadata = (
            prog.state in METADATA_QB_STATES
            or (job.total_size == 0 and prog.size <= 0 and prog.progress < 1.0)
        )
        if waiting_metadata and _is_metadata_timed_out(job, cfg.magnet_metadata_timeout_sec):
            await _fail_metadata_timeout(job, store, qb, cfg)
            return

        meta_updates: dict[str, Any] = {}
        if not waiting_metadata and job.total_size == 0 and prog.size > 0:
            meta_updates["total_size"] = prog.size
            if prog.name and prog.name.strip():
                meta_updates["name"] = prog.name.strip()[:255]

        if prog.progress >= 1.0 and prog.state in COMPLETED_QB_STATES:
            if meta_updates:
                job = store.update_job(job.id, **meta_updates)
            await _handle_completion(
                job,
                prog.content_path or job.content_path,
                store,
                qb,
                cfg,
                background_tasks=background_tasks,
            )
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
    elif job.state in ("completed_in_client", "moving", "post_processing"):
        await _handle_completion(
            job,
            job.content_path,
            store,
            qb,
            cfg,
            background_tasks=background_tasks,
        )


async def poll_once(
    store: JobStore,
    qb: QBittorrentClient,
    cfg: Settings,
    background_tasks: set[asyncio.Task[Any]] | None = None,
) -> None:
    """Execute a single polling and state-transition cycle."""
    active_jobs = store.list_active_jobs()
    if not active_jobs:
        return

    poll_hashes = [j.info_hash for j in active_jobs if j.state in ("submitted", "downloading")]
    torrents_dict: dict[str, Any] = {}
    if poll_hashes:
        try:
            torrents_dict = await qb.get_torrents(poll_hashes)
        except Exception as exc:
            logger.warning("Failed to query torrents from qBittorrent: %s", exc)

    for job in active_jobs:
        try:
            await _process_job(
                job,
                torrents_dict,
                store,
                qb,
                cfg,
                background_tasks=background_tasks,
            )
        except Exception as exc:
            logger.exception("Unexpected error processing job %s (id=%d): %s", job.name, job.id, exc)


async def run_worker_loop(
    store: JobStore,
    qb: QBittorrentClient,
    cfg: Settings,
    stop_event: asyncio.Event,
    interval_sec: float = 3.0,
) -> None:
    """Run the background worker loop until stop_event is set."""
    logger.info("Starting background worker loop (interval=%ss)", interval_sec)
    background_tasks: set[asyncio.Task[Any]] = set()
    try:
        while not stop_event.is_set():
            try:
                await poll_once(store, qb, cfg, background_tasks=background_tasks)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Unexpected error in worker poll_once: %s", exc)

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
            except asyncio.TimeoutError:
                pass
    finally:
        if background_tasks:
            await asyncio.gather(*list(background_tasks), return_exceptions=True)
