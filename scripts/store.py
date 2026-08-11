"""SQLite-State: seen.db mit jobs/runs. Upsert idempotent, "nur Neues"-Query."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "seen.sqlite"

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_hash TEXT UNIQUE NOT NULL,
    canonical_url TEXT,
    source TEXT,
    source_job_id TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    remote INTEGER DEFAULT 0,
    url TEXT,
    description TEXT,
    salary TEXT,
    posted_at TEXT,
    tech_tags TEXT,
    employment_type TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    seen_count INTEGER DEFAULT 1,
    score INTEGER DEFAULT 0,
    score_reason TEXT,
    status TEXT DEFAULT 'new',
    notified_at TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_canonical_url ON jobs(canonical_url);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_notified_at ON jobs(notified_at);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started TEXT NOT NULL,
    finished TEXT,
    sources_ok INTEGER DEFAULT 0,
    sources_failed INTEGER DEFAULT 0,
    jobs_new INTEGER DEFAULT 0,
    jobs_seen INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    note TEXT
);

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()
    return conn


def upsert(conn: sqlite3.Connection, job: dict) -> bool:
    """Insert oder last_seen/seen_count-Update. True = Job ist NEU."""
    now = _now()
    tech_tags = json.dumps(job.get("tech_tags") or [], ensure_ascii=False)
    cur = conn.execute(
        """
        INSERT INTO jobs (dedup_hash, canonical_url, source, source_job_id,
            title, company, location, remote, url, description, salary,
            posted_at, tech_tags, employment_type, first_seen, last_seen,
            seen_count, score, score_reason, status, raw_json)
        VALUES (:dedup_hash, :canonical_url, :source, :source_job_id,
            :title, :company, :location, :remote, :url, :description, :salary,
            :posted_at, :tech_tags, :employment_type, :now, :now,
            1, :score, :score_reason, :status, :raw_json)
        ON CONFLICT(dedup_hash) DO UPDATE SET
            last_seen = :now,
            seen_count = seen_count + 1
        """,
        {
            "dedup_hash": job["dedup_hash"],
            "canonical_url": job.get("canonical_url"),
            "source": job.get("source"),
            "source_job_id": job.get("source_job_id"),
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "remote": int(bool(job.get("remote"))),
            "url": job.get("url"),
            "description": job.get("description"),
            "salary": job.get("salary"),
            "posted_at": job.get("posted_at"),
            "tech_tags": tech_tags,
            "employment_type": job.get("employment_type"),
            "now": now,
            "score": job.get("score", 0),
            "score_reason": job.get("score_reason"),
            "status": job.get("status", "new"),
            "raw_json": job.get("raw_json"),
        },
    )
    is_new = conn.execute(
        "SELECT seen_count FROM jobs WHERE dedup_hash=?", (job["dedup_hash"],)
    ).fetchone()[0] == 1
    conn.commit()
    return is_new


def new_for_digest(conn: sqlite3.Connection, min_score: int, limit: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM jobs
        WHERE notified_at IS NULL AND status = 'new' AND score >= ?
        ORDER BY score DESC LIMIT ?
        """,
        (min_score, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_notified(conn: sqlite3.Connection, ids: list[int]) -> None:
    now = _now()
    conn.executemany("UPDATE jobs SET notified_at=? WHERE id=?", [(now, i) for i in ids])
    conn.commit()


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO runs (started) VALUES (?)", (_now(),))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, *, sources_ok: int,
               sources_failed: int, jobs_new: int, jobs_seen: int,
               status: str, note: str = "") -> None:
    conn.execute(
        """
        UPDATE runs SET finished=?, sources_ok=?, sources_failed=?,
            jobs_new=?, jobs_seen=?, status=?, note=?
        WHERE id=?
        """,
        (_now(), sources_ok, sources_failed, jobs_new, jobs_seen, status, note, run_id),
    )
    conn.commit()
