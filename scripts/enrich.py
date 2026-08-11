"""Volltext-Nachladen für Score-Grenzfälle (20–39) — Arbeitsteilung wie beim
Portal-Ingest: CLAUDE scrapt die URLs (Firecrawl-MCP), dieses Skript bleibt
deterministisch.

Ablauf pro Lauf (siehe SKILL.md):
  python scripts/enrich.py list            -> Kandidaten (id, score, url, titel)
  (Claude scrapt jede URL als Markdown/Text -> Datei)
  python scripts/enrich.py apply <id> <textdatei>   -> Text + Re-Score
  python scripts/enrich.py mark-dead <id>           -> URL gibt nichts her,
                                                       nicht erneut versuchen

Kandidaten-Kriterium: status='new', Score im Band, Beschreibung < 200 Zeichen
(nach apply/mark-dead fällt der Job automatisch aus der Liste). Deckel
MAX_PER_RUN schützt das Credit-Budget.
"""
from __future__ import annotations

import json
import sqlite3
import sys

import normalize
import score
import store

BAND = (20, 39)
MAX_PER_RUN = 15
# < 600: fängt fehlende Texte UND abgeschnittene Snippets (Adzuna exakt 500,
# StepStone ~360, LinkedIn 0); echte Volltexte (Arbeitnow 3000+) bleiben draußen
MIN_DESCRIPTION_CHARS = 600
DEAD_MARKER = "[enrich: kein Volltext verfügbar]"


def candidates(conn: sqlite3.Connection, limit: int = MAX_PER_RUN) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, score, url, title, company FROM jobs
        WHERE status = 'new' AND score BETWEEN ? AND ?
          AND LENGTH(COALESCE(description, '')) < ?
        ORDER BY score DESC, id ASC LIMIT ?
        """,
        (BAND[0], BAND[1], MIN_DESCRIPTION_CHARS, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def apply(conn: sqlite3.Connection, job_id: int, text: str,
          profile: dict | None = None,
          seed_companies: list[str] | None = None) -> tuple[int, int]:
    """Volltext setzen, Tech-Tags neu extrahieren, neu scoren.

    Gibt (alter_score, neuer_score) zurück. notified_at bleibt NULL, damit
    Jobs, die jetzt über die Schwelle rutschen, im nächsten Digest landen.
    """
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"Job {job_id} nicht gefunden")
    job = dict(row)
    old_score = job["score"]

    text = text.strip()
    job["description"] = text
    anchors = list(normalize.default_anchors())
    job["tech_tags"] = normalize.extract_tech_tags(
        f"{job.get('title') or ''} {text}", anchors)
    job["remote"] = bool(job["remote"])
    job["status"] = "new"  # score_job entscheidet neu
    score.score_job(job, profile, seed_companies=seed_companies)

    conn.execute(
        """
        UPDATE jobs SET description=?, tech_tags=?, score=?, score_reason=?,
                        status=?
        WHERE id=?
        """,
        (job["description"], json.dumps(job["tech_tags"], ensure_ascii=False),
         job["score"], job["score_reason"], job["status"], job_id),
    )
    conn.commit()
    return old_score, job["score"]


def mark_dead(conn: sqlite3.Connection, job_id: int) -> None:
    """URL liefert keinen Text — Marker setzen, damit der Job nicht bei jedem
    Lauf erneut versucht wird. Score/Status bleiben unverändert."""
    conn.execute("UPDATE jobs SET description=? WHERE id=?",
                 (DEAD_MARKER.ljust(MIN_DESCRIPTION_CHARS), job_id))
    conn.commit()


def main(argv: list[str]) -> int:
    conn = store.init_db()
    if argv and argv[0] == "list":
        limit = int(argv[1]) if len(argv) > 1 else MAX_PER_RUN
        rows = candidates(conn, limit=limit)
        for r in rows:
            print(f"{r['id']}\t{r['score']}\t{r['url']}\t{r['title']} | {r['company']}")
        print(f"# {len(rows)} Kandidaten (Band {BAND[0]}–{BAND[1]}, Deckel {limit})",
              file=sys.stderr)
        return 0
    if len(argv) >= 3 and argv[0] == "apply":
        from pathlib import Path
        old, new = apply(conn, int(argv[1]),
                         Path(argv[2]).read_text(encoding="utf-8"))
        marker = " -> DIGEST" if new >= 40 > old else ""
        print(f"Job {argv[1]}: Score {old} -> {new}{marker}")
        return 0
    if len(argv) >= 2 and argv[0] == "mark-dead":
        mark_dead(conn, int(argv[1]))
        print(f"Job {argv[1]} als 'kein Volltext' markiert.")
        return 0
    print("Nutzung: enrich.py list [n] | apply <id> <textdatei> | mark-dead <id>",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
