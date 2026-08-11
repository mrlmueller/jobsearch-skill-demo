"""Tests für mark.py — Bewerbungsstatus als Einzeiler."""
import pytest

import mark
import store


def seed(conn, dedup_hash="h1", **over):
    job = {"dedup_hash": dedup_hash, "title": "Werkstudent Dev", "company": "Acme",
           "location": "Ulm", "url": "https://x.de/1", "score": 80,
           "score_reason": "gut", "status": "new", "raw_json": "{}"}
    job.update(over)
    store.upsert(conn, job)
    return conn.execute("SELECT id FROM jobs WHERE dedup_hash=?",
                        (dedup_hash,)).fetchone()[0]


def test_mark_sets_status(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    job_id = seed(conn)
    mark.mark(conn, job_id, "applied")
    assert conn.execute("SELECT status FROM jobs WHERE id=?",
                        (job_id,)).fetchone()[0] == "applied"


def test_mark_rejects_unknown_status(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    job_id = seed(conn)
    with pytest.raises(ValueError):
        mark.mark(conn, job_id, "vielleicht")


def test_mark_unknown_id_raises(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    with pytest.raises(ValueError):
        mark.mark(conn, 999, "applied")


def test_list_marked(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    a = seed(conn, dedup_hash="a")
    seed(conn, dedup_hash="b")
    mark.mark(conn, a, "applied")
    rows = mark.list_marked(conn)
    assert [r["id"] for r in rows] == [a]
    assert rows[0]["status"] == "applied"
