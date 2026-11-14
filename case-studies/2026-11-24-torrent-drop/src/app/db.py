from __future__ import annotations

import contextlib
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTIVE_STATES: set[str] = {
    "submitted",
    "downloading",
    "completed_in_client",
    "moving",
    "post_processing",
    "notifying",
}


class DuplicateActiveJobError(Exception):
    """Raised when an active job for the same info_hash already exists."""
    pass


@dataclass
class JobRecord:
    id: int
    info_hash: str
    name: str
    category: str
    total_size: int
    state: str
    progress: float
    dlspeed: int
    eta: int
    content_path: str | None = None
    dest_path: str | None = None
    subtitle_summary: str | None = None
    warning: str | None = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""


class JobStore:
    _COLUMNS = (
        "id, info_hash, name, category, total_size, state, progress, dlspeed, eta, "
        "content_path, dest_path, subtitle_summary, warning, error, created_at, updated_at"
    )

    _ALLOWED_UPDATE_FIELDS = {
        "info_hash",
        "name",
        "category",
        "total_size",
        "state",
        "progress",
        "dlspeed",
        "eta",
        "content_path",
        "dest_path",
        "subtitle_summary",
        "warning",
        "error",
    }

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with contextlib.closing(self._connect()) as conn:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        info_hash TEXT NOT NULL,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        total_size INTEGER NOT NULL,
                        state TEXT NOT NULL,
                        progress REAL NOT NULL DEFAULT 0.0,
                        dlspeed INTEGER NOT NULL DEFAULT 0,
                        eta INTEGER NOT NULL DEFAULT 0,
                        content_path TEXT,
                        dest_path TEXT,
                        subtitle_summary TEXT,
                        warning TEXT,
                        error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_info_hash_state ON jobs(info_hash, state);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);"
                )
                conn.commit()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            info_hash=row["info_hash"],
            name=row["name"],
            category=row["category"],
            total_size=row["total_size"],
            state=row["state"],
            progress=float(row["progress"]),
            dlspeed=int(row["dlspeed"]),
            eta=int(row["eta"]),
            content_path=row["content_path"],
            dest_path=row["dest_path"],
            subtitle_summary=row["subtitle_summary"],
            warning=row["warning"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_job(self, info_hash: str, name: str, category: str, total_size: int) -> JobRecord:
        norm_hash = info_hash.strip().lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        active_placeholders = ",".join("?" for _ in ACTIVE_STATES)
        check_query = f"SELECT id FROM jobs WHERE info_hash = ? AND state IN ({active_placeholders})"

        with self._lock:
            with contextlib.closing(self._connect()) as conn:
                existing = conn.execute(check_query, (norm_hash, *ACTIVE_STATES)).fetchone()
                if existing:
                    raise DuplicateActiveJobError(
                        f"Active job already exists for info_hash '{info_hash}' (job ID: {existing['id']})"
                    )

                cur = conn.execute(
                    """
                    INSERT INTO jobs (
                        info_hash, name, category, total_size,
                        state, progress, dlspeed, eta,
                        content_path, dest_path, subtitle_summary, warning, error,
                        created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?,
                        'submitted', 0.0, 0, 0,
                        NULL, NULL, NULL, NULL, NULL,
                        ?, ?
                    )
                    """,
                    (norm_hash, name, category, total_size, now_iso, now_iso),
                )
                job_id = cur.lastrowid
                conn.commit()

                row = conn.execute(
                    f"SELECT {self._COLUMNS} FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
                return self._row_to_record(row)

    def get_job(self, job_id: int) -> JobRecord | None:
        with self._lock:
            with contextlib.closing(self._connect()) as conn:
                row = conn.execute(
                    f"SELECT {self._COLUMNS} FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_record(row)

    def list_jobs(self, limit: int = 50) -> list[JobRecord]:
        with self._lock:
            with contextlib.closing(self._connect()) as conn:
                cur = conn.execute(
                    f"SELECT {self._COLUMNS} FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
                )
                return [self._row_to_record(row) for row in cur.fetchall()]

    def list_active_jobs(self) -> list[JobRecord]:
        active_placeholders = ",".join("?" for _ in ACTIVE_STATES)
        query = f"SELECT {self._COLUMNS} FROM jobs WHERE state IN ({active_placeholders}) ORDER BY id ASC"
        with self._lock:
            with contextlib.closing(self._connect()) as conn:
                cur = conn.execute(query, tuple(ACTIVE_STATES))
                return [self._row_to_record(row) for row in cur.fetchall()]

    def update_job(self, job_id: int, **fields: Any) -> JobRecord:
        invalid = set(fields.keys()) - self._ALLOWED_UPDATE_FIELDS
        if invalid:
            raise ValueError(f"Invalid field(s) for job update: {invalid}")

        now_iso = datetime.now(timezone.utc).isoformat()
        set_parts = [f"{k} = ?" for k in fields.keys()] + ["updated_at = ?"]
        set_clause = ", ".join(set_parts)
        params = list(fields.values()) + [now_iso, job_id]

        with self._lock:
            with contextlib.closing(self._connect()) as conn:
                cur = conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", params)
                if cur.rowcount == 0:
                    raise KeyError(f"Job with id {job_id} not found")
                conn.commit()

                row = conn.execute(
                    f"SELECT {self._COLUMNS} FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
                return self._row_to_record(row)

    def delete_job(self, job_id: int) -> bool:
        with self._lock:
            with contextlib.closing(self._connect()) as conn:
                cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                conn.commit()
                return cur.rowcount > 0
