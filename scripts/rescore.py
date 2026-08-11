"""Bestehende DB-Jobs neu bewerten (nach Änderungen an profile.yaml).

Nur automatische Status ('new'/'ignored') werden angefasst — manuelle
Markierungen (applied/rejected/interesting) bleiben unangetastet.
notified_at bleibt erhalten: bereits gemeldete Jobs tauchen nicht erneut
im Digest auf, nur ihre Score-Werte werden aktuell gehalten.

Aufruf: python scripts/rescore.py
"""
from __future__ import annotations

import json
import sqlite3

import score
import store


def rescore_all(conn: sqlite3.Connection, profile: dict | None = None,
                seed_companies: list[str] | None = None) -> int:
    """Bewertet alle new/ignored-Jobs neu. Gibt Anzahl geänderter Zeilen zurück."""
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status IN ('new', 'ignored')").fetchall()
    changed = 0
    for row in rows:
        job = dict(row)
        job["tech_tags"] = json.loads(job.get("tech_tags") or "[]")
        job["remote"] = bool(job["remote"])
        old = (job["score"], job["score_reason"], job["status"])
        job["status"] = "new"  # score_job entscheidet neu über ignored
        score.score_job(job, profile, seed_companies=seed_companies)
        if (job["score"], job["score_reason"], job["status"]) != old:
            conn.execute(
                "UPDATE jobs SET score=?, score_reason=?, status=? WHERE id=?",
                (job["score"], job["score_reason"], job["status"], row["id"]))
            changed += 1
    conn.commit()
    return changed


if __name__ == "__main__":
    conn = store.init_db()
    n = rescore_all(conn)
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    print(f"{n} von {total} Jobs neu bewertet (Status new/ignored).")
