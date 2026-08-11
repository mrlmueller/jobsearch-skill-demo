"""Tests für store.py — SQLite-State (Manifest §1)."""
import sqlite3

import pytest

import store


@pytest.fixture
def db(tmp_path):
    conn = store.init_db(tmp_path / "seen.sqlite")
    yield conn
    conn.close()


def make_job(**over):
    job = {
        "dedup_hash": "abc123",
        "canonical_url": "https://example.com/job/1",
        "source": "arbeitsagentur",
        "source_job_id": "REF-1",
        "title": "Werkstudent Softwareentwicklung",
        "company": "Acme GmbH",
        "location": "Ulm",
        "remote": False,
        "url": "https://example.com/job/1?utm_source=x",
        "description": "Python, Docker",
        "salary": None,
        "posted_at": "2026-07-20",
        "tech_tags": ["python", "docker"],
        "employment_type": "werkstudent",
        "score": 60,
        "score_reason": "2 Tech-Tags",
        "raw_json": "{}",
    }
    job.update(over)
    return job


def test_init_db_creates_tables_and_wal(db):
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"jobs", "runs", "schema_version"} <= tables
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_upsert_new_job_returns_true(db):
    assert store.upsert(db, make_job()) is True
    row = db.execute("SELECT seen_count, status FROM jobs").fetchone()
    assert tuple(row) == (1, "new")


def test_upsert_same_hash_increments_seen_count(db):
    store.upsert(db, make_job())
    assert store.upsert(db, make_job()) is False
    rows = [tuple(r) for r in db.execute("SELECT seen_count FROM jobs")]
    assert rows == [(2,)]  # ein Datensatz, kein Duplikat


def test_new_for_digest_filters_and_sorts(db):
    store.upsert(db, make_job(dedup_hash="a", score=80))
    store.upsert(db, make_job(dedup_hash="b", score=50))
    store.upsert(db, make_job(dedup_hash="c", score=20))          # unter min_score
    store.upsert(db, make_job(dedup_hash="d", score=90, status="ignored"))
    jobs = store.new_for_digest(db, min_score=40, limit=10)
    assert [j["dedup_hash"] for j in jobs] == ["a", "b"]


def test_mark_notified_removes_from_digest(db):
    store.upsert(db, make_job(dedup_hash="a", score=80))
    jobs = store.new_for_digest(db, min_score=40, limit=10)
    store.mark_notified(db, [j["id"] for j in jobs])
    assert store.new_for_digest(db, min_score=40, limit=10) == []


def test_run_lifecycle(db):
    run_id = store.start_run(db)
    store.finish_run(db, run_id, sources_ok=2, sources_failed=0,
                     jobs_new=5, jobs_seen=3, status="ok", note="")
    row = db.execute(
        "SELECT sources_ok, jobs_new, status, finished FROM runs WHERE id=?",
        (run_id,)).fetchone()
    assert row[0] == 2 and row[1] == 5 and row[2] == "ok"
    assert row[3] is not None
