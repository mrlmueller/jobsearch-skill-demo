"""Bewerbungsstatus setzen — der Feedback-Loop des Nutzers.

  python scripts/mark.py <id> applied|rejected|interesting|ignored|new
  python scripts/mark.py list          -> alle manuell markierten Jobs

Manuelle Status überleben rescore.py und Upserts; der Claude-Layer nutzt
sie beim Relevanz-Check, um über die Wochen schärfer zu kuratieren.
"""
from __future__ import annotations

import sqlite3
import sys

import store

ALLOWED = ("new", "interesting", "applied", "rejected", "ignored")
MANUAL = ("interesting", "applied", "rejected")


def mark(conn: sqlite3.Connection, job_id: int, status: str) -> dict:
    if status not in ALLOWED:
        raise ValueError(f"Status {status!r} unbekannt — erlaubt: {', '.join(ALLOWED)}")
    row = conn.execute("SELECT id, title, company FROM jobs WHERE id=?",
                       (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"Job {job_id} nicht gefunden")
    conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
    conn.commit()
    return dict(row)


def list_marked(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        f"""SELECT id, status, title, company, location, url FROM jobs
            WHERE status IN ({','.join('?' * len(MANUAL))})
            ORDER BY status, id""", MANUAL).fetchall()
    return [dict(r) for r in rows]


def main(argv: list[str]) -> int:
    conn = store.init_db()
    if argv and argv[0] == "list":
        rows = list_marked(conn)
        if not rows:
            print("Noch nichts markiert.")
        for r in rows:
            print(f"{r['id']}\t{r['status']}\t{r['title']} | {r['company']}")
        return 0
    if len(argv) >= 2:
        job = mark(conn, int(argv[0]), argv[1])
        print(f"Job {argv[0]} ({job['title']} | {job['company']}) -> {argv[1]}")
        return 0
    print("Nutzung: mark.py <id> <status> | mark.py list", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
