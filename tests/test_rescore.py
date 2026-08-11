"""Tests für rescore.py — Neu-Bewertung nach Configänderung."""
import json

import rescore
import store


PROFILE = {
    "person": {"regions_in_radius": ["Ulm"], "remote_ok": True},
    "must": {"employment_types": ["werkstudent"], "role_is_tech": True,
             "location_in_radius_or_remote": True},
    "plus": {"tech_tag_match": 10, "startup_or_small_team": 15,
             "ki_affine_firma": 15, "no_cover_letter_or_takehome": 10,
             "flexible_hours_or_remote": 10, "uebernahme_perspektive": 10,
             "from_companies_seed": 10},
    "minus_flags": {},
    "exclude_keywords": ["senior"],
}


def seed_job(conn, **over):
    job = {"dedup_hash": over.pop("dedup_hash", "h1"),
           "title": "Werkstudent Softwareentwicklung", "company": "Acme",
           "location": "Berlin", "remote": False, "url": "https://x.de/1",
           "description": "Python", "tech_tags": ["python"],
           "employment_type": "werkstudent", "score": 0,
           "score_reason": "außerhalb Radius, nicht remote",
           "status": "ignored", "raw_json": "{}"}
    job.update(over)
    store.upsert(conn, job)
    return job


def test_rescore_updates_ignored_jobs(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    seed_job(conn, dedup_hash="a", location="Berlin")            # bleibt ignored
    seed_job(conn, dedup_hash="b", location="Ulm")               # wird durch neues Profil ok
    # in der DB steht b noch als ignored (z. B. weil Ulm früher nicht in der Liste war)
    changed = rescore.rescore_all(conn, profile=PROFILE, seed_companies=[])
    rows = {r["dedup_hash"]: r for r in
            (dict(x) for x in conn.execute("SELECT * FROM jobs"))}
    assert rows["a"]["status"] == "ignored"
    assert rows["b"]["status"] == "new"
    assert rows["b"]["score"] > 0
    assert changed == 1     # nur b hat sich geändert


def test_rescore_preserves_manual_status(tmp_path):
    conn = store.init_db(tmp_path / "s.sqlite")
    seed_job(conn, dedup_hash="c", location="Ulm", status="applied")
    rescore.rescore_all(conn, profile=PROFILE, seed_companies=[])
    status = conn.execute("SELECT status FROM jobs WHERE dedup_hash='c'").fetchone()[0]
    assert status == "applied"      # manuelle Status bleiben unangetastet
