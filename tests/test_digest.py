"""Tests für digest.py — Markdown-Rendering + Schreiben/mark_notified."""
import digest
import store


def make_job(i, score=50, **over):
    j = {
        "id": i, "title": f"Werkstudent Dev {i}", "company": "Acme GmbH",
        "location": "Ulm", "remote": False, "score": score,
        "score_reason": "2 Tech-Tags (+20)", "url": f"https://x.de/{i}",
        "source": "arbeitsagentur",
    }
    j.update(over)
    return j


META = {"date": "2026-07-23", "sources_ok": ["arbeitsagentur", "arbeitnow"],
        "sources_failed": [], "jobs_new": 2, "jobs_total": 40}


def test_render_contains_header_and_items():
    md = digest.render_digest([make_job(1, 80), make_job(2, 50, remote=True)], META)
    assert "2026-07-23" in md
    assert "Quellen: 2 ok, 0 fehlgeschlagen" in md
    assert "Werkstudent Dev 1" in md and "**80**" in md
    assert "Remote" in md                     # remote-Job wird als Remote gelabelt
    assert "https://x.de/1" in md


def test_render_failed_sources_footnote():
    meta = dict(META, sources_failed=["arbeitnow"])
    md = digest.render_digest([make_job(1)], meta)
    assert "arbeitnow" in md and "fehlgeschlagen" in md.lower()


def test_render_skipped_sources_footnote():
    meta = dict(META, sources_skipped=["adzuna (kein Key)"])
    md = digest.render_digest([make_job(1)], meta)
    assert "adzuna" in md and "übersprungen" in md.lower()


def test_render_empty_run():
    md = digest.render_digest([], META)
    assert "keine neuen" in md.lower()


def test_write_digest_marks_notified(tmp_path):
    conn = store.init_db(tmp_path / "seen.sqlite")
    store.upsert(conn, {"dedup_hash": "h1", "title": "Werkstudent Dev",
                        "company": "Acme", "location": "Ulm", "url": "https://x.de/1",
                        "score": 80, "score_reason": "gut", "status": "new",
                        "raw_json": "{}"})
    path, jobs = digest.write_digest(conn, META, min_score=40, limit=10,
                                     out_dir=tmp_path)
    assert path.exists()
    assert len(jobs) == 1 and jobs[0]["title"] == "Werkstudent Dev"
    assert "Werkstudent Dev" in path.read_text(encoding="utf-8")
    # zweiter Aufruf: nichts Neues mehr
    assert store.new_for_digest(conn, min_score=40, limit=10) == []
    conn.close()
