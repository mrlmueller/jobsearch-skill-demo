"""Tests für enrich.py — Volltext-Nachladen für Score-Grenzfälle (20–39)."""
import json

import enrich
import store

PROFILE = {
    "person": {"regions_in_radius": ["Ulm", "Augsburg"], "remote_ok": True},
    "must": {"employment_types": ["werkstudent", "teilzeit", "praktikum",
                                  "working student", "part-time", "intern"],
             "role_is_tech": True, "location_in_radius_or_remote": True},
    "plus": {"tech_tag_match": 10, "startup_or_small_team": 15,
             "ki_affine_firma": 15, "no_cover_letter_or_takehome": 10,
             "flexible_hours_or_remote": 10, "uebernahme_perspektive": 10,
             "from_companies_seed": 10},
    "minus_flags": {},
    "exclude_keywords": ["senior"],
}


def seed(conn, **over):
    job = {"dedup_hash": over.pop("dedup_hash", "h1"),
           "title": "Werkstudent Softwareentwicklung (m/w/d)", "company": "Acme",
           "location": "Augsburg", "remote": False, "url": "https://x.de/1",
           "description": "kurz", "tech_tags": ["python"],
           "employment_type": "werkstudent", "score": 25,
           "score_reason": "1 Tech-Tags (+10)...", "status": "new",
           "raw_json": "{}"}
    job.update(over)
    store.upsert(conn, job)
    return conn.execute("SELECT id FROM jobs WHERE dedup_hash=?",
                        (job["dedup_hash"],)).fetchone()[0]


def test_candidates_band_cap_and_short_description(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    a = seed(conn, dedup_hash="a", score=35)                       # Kandidat
    seed(conn, dedup_hash="b", score=55)                           # über Band
    seed(conn, dedup_hash="c", score=10)                           # unter Band
    seed(conn, dedup_hash="d", score=30, status="ignored")         # kein 'new'
    seed(conn, dedup_hash="e", score=30, description="x" * 800)    # hat Volltext
    seed(conn, dedup_hash="f", score=30, description="y" * 500)    # Adzuna-Snippet -> Kandidat
    rows = enrich.candidates(conn, limit=10)
    f = conn.execute("SELECT id FROM jobs WHERE dedup_hash='f'").fetchone()[0]
    assert [r["id"] for r in rows] == [a, f]   # beide 20–39 ohne echten Volltext
    conn.close()


def test_candidates_respects_limit_and_orders_by_score(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    seed(conn, dedup_hash="a", score=22)
    b = seed(conn, dedup_hash="b", score=38)
    seed(conn, dedup_hash="c", score=25)
    rows = enrich.candidates(conn, limit=1)
    assert [r["id"] for r in rows] == [b]
    conn.close()


def test_apply_updates_description_tags_and_score(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    job_id = seed(conn, dedup_hash="a", score=25)
    text = ("Wir sind ein kleines Team und suchen dich! Stack: Python, FastAPI, "
            "Docker, TypeScript und React. Flexible Arbeitszeiten, KI-Projekte.")
    old, new = enrich.apply(conn, job_id, text, profile=PROFILE, seed_companies=[])
    row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    assert old == 25
    assert new > 40                       # rutscht über die Digest-Schwelle
    assert row["score"] == new
    assert "FastAPI" in row["description"]
    tags = json.loads(row["tech_tags"])
    assert "fastapi" in tags and "react" in tags
    assert row["status"] == "new"
    assert row["notified_at"] is None     # taucht im nächsten Digest auf
    conn.close()


def test_mark_dead_removes_from_candidates(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    job_id = seed(conn, dedup_hash="a", score=30)
    enrich.mark_dead(conn, job_id)
    assert enrich.candidates(conn, limit=10) == []
    # Score/Status bleiben unangetastet
    row = conn.execute("SELECT score, status FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert tuple(row) == (30, "new")
    conn.close()
