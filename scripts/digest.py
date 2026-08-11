"""Digest: "nur Neues"-Query -> datierte Markdown-Datei -> mark_notified."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import store
import envutil

ROOT = Path(__file__).parent.parent
DIGEST_DIR = ROOT / "digests"


def _mode_hint(job: dict) -> str:
    reason = job.get("score_reason") or ""
    if "no_cover_letter" in reason:
        return " · **ohne Anschreiben**"
    if "live_leetcode" in reason:
        return " · ⚠ Live-Coding"
    return ""


def render_digest(jobs: list[dict], meta: dict) -> str:
    ok, failed = meta["sources_ok"], meta["sources_failed"]
    lines = [
        f"# Job-Digest {meta['date']}",
        "",
        f"Quellen: {len(ok)} ok, {len(failed)} fehlgeschlagen · "
        f"**{meta['jobs_new']} neu** · {meta['jobs_total']} gesamt in DB",
        "",
    ]
    if not jobs:
        lines.append("_Keine neuen Treffer über der Score-Schwelle._")
    for j in jobs:
        ort = "Remote" if j.get("remote") else (j.get("location") or "?")
        lines += [
            f"## {j['title']}",
            f"**{j.get('company') or '?'}** · {ort} · Score **{j['score']}**"
            f" · _{j.get('source')}_{_mode_hint(j)}",
            f"{j.get('score_reason') or ''}",
            f"→ {j.get('url')}",
            "",
        ]
    footnotes = []
    if failed:
        footnotes.append(f"⚠ Fehlgeschlagene Quellen: {', '.join(failed)}")
    skipped = meta.get("sources_skipped") or []
    if skipped:
        footnotes.append(f"Übersprungen: {', '.join(skipped)}")
    if footnotes:
        lines += ["---"] + footnotes
    return "\n".join(lines) + "\n"


def write_digest(conn: sqlite3.Connection, meta: dict, *, min_score: int,
                 limit: int, out_dir: Path = DIGEST_DIR) -> tuple[Path, list[dict]]:
    """Schreibt den Digest, markiert notified. Gibt (Pfad, Digest-Jobs) zurück."""
    jobs = store.new_for_digest(conn, min_score=min_score, limit=limit)
    md = render_digest(jobs, meta)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{meta['date']}_digest.md"
    if path.exists():  # zweiter Lauf am selben Tag: anhängen statt überschreiben
        md = path.read_text(encoding="utf-8") + "\n---\n\n" + md
    path.write_text(md, encoding="utf-8")
    store.mark_notified(conn, [j["id"] for j in jobs])
    return path, jobs


def build_meta(conn: sqlite3.Connection, sources_ok: list[str],
               sources_failed: list[str], jobs_new: int) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    return {"date": date.today().isoformat(), "sources_ok": sources_ok,
            "sources_failed": sources_failed, "jobs_new": jobs_new,
            "jobs_total": total}


if __name__ == "__main__":
    # Nach-Digest, z. B. nach enrich.py: schreibt alle noch nicht gemeldeten
    # Treffer über der Schwelle als weiteren Block in die Tagesdatei.
    import yaml

    import store as _store

    conn = _store.init_db()
    with open(envutil.profile_path(), encoding="utf-8") as f:
        scoring = (yaml.safe_load(f).get("scoring") or {})
    pending = _store.new_for_digest(
        conn, min_score=scoring.get("min_score_for_digest", 40),
        limit=scoring.get("digest_max_items", 40))
    if not pending:
        print("Keine ungemeldeten Treffer über der Schwelle — kein Nach-Digest.")
    else:
        meta = build_meta(conn, [], [], jobs_new=len(pending))
        path, jobs = write_digest(
            conn, meta, min_score=scoring.get("min_score_for_digest", 40),
            limit=scoring.get("digest_max_items", 40))
        print(f"Nach-Digest: {len(jobs)} Treffer -> {path}")
