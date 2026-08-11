"""Orchestrator: fetch -> normalize -> dedup -> score -> store -> digest.

Aufruf: python scripts/run.py [--no-digest]
Keine Quelle darf den Lauf abbrechen (try/except je Quelle).

Nur Key-lose API-Quellen — Portale scrapt CLAUDE per Firecrawl-MCP und
speist sie über scrape_portals.py ingest ein (VOR run.py, dann landet
alles in einem Digest). Ablauf: siehe .claude/skills/jobsuche/SKILL.md.
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

import dedup
import digest
import fetch_adzuna
import fetch_arbeitnow
import fetch_arbeitsagentur
import fetch_ats
import fetch_linkedin
import fetch_remote
import normalize
import score
import store
import envutil

ROOT = Path(__file__).parent.parent
RUNS_DIR = ROOT / "data" / "runs"

SOURCES = [
    ("arbeitsagentur", fetch_arbeitsagentur.fetch),
    ("arbeitnow", fetch_arbeitnow.fetch),
    ("himalayas", fetch_remote.fetch_himalayas),
    ("jobicy", fetch_remote.fetch_jobicy),
    ("remoteok", fetch_remote.fetch_remoteok),
    ("remotive", fetch_remote.fetch_remotive),
    ("adzuna", fetch_adzuna.fetch),  # überspringt sich selbst ohne Key in .env
    ("linkedin", fetch_linkedin.fetch),  # Guest-Endpoint, kein Login
    ("ats", fetch_ats.fetch),  # verdeckter Markt: Seed-Firmen-Feeds (Phase 3)
]


def load_profile() -> dict:
    with open(envutil.profile_path(), encoding="utf-8") as f:
        return yaml.safe_load(f)


def dump_raw(name: str, raws: list[dict], stamp: str) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{stamp}_{name}.json"
    path.write_text(json.dumps(raws, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    profile = load_profile()
    conn = store.init_db()
    run_id = store.start_run(conn)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")

    sources_ok: list[str] = []
    sources_failed: list[str] = []
    all_raw: list[dict] = []
    for name, fetch_fn in SOURCES:
        if name == "adzuna" and not fetch_adzuna.has_credentials():
            print(f"[{name}] übersprungen — kein Key in .env")
            continue
        try:
            raws = fetch_fn()
            dump_raw(name, raws, stamp)
            all_raw.extend(raws)
            sources_ok.append(name)
            print(f"[{name}] {len(raws)} Roh-Jobs")
        except Exception as e:
            sources_failed.append(name)
            print(f"[{name}] FEHLGESCHLAGEN: {e}", file=sys.stderr)
            traceback.print_exc()

    jobs = normalize.normalize_all(all_raw)
    deduped = dedup.dedup_all(jobs)
    scored = score.score_all(deduped)

    jobs_new = jobs_seen = 0
    for job in scored:
        if store.upsert(conn, job):
            jobs_new += 1
        else:
            jobs_seen += 1

    status = "ok" if not sources_failed else (
        "partial" if sources_ok else "failed")
    store.finish_run(conn, run_id, sources_ok=len(sources_ok),
                     sources_failed=len(sources_failed), jobs_new=jobs_new,
                     jobs_seen=jobs_seen, status=status)

    print(f"\nLauf {run_id}: {len(all_raw)} roh -> {len(deduped)} dedupliziert "
          f"-> {jobs_new} neu, {jobs_seen} bekannt ({status})")

    if "--no-digest" not in sys.argv:
        meta = digest.build_meta(conn, sources_ok, sources_failed, jobs_new)
        scoring = profile.get("scoring") or {}
        path, digest_jobs = digest.write_digest(
            conn, meta,
            min_score=scoring.get("min_score_for_digest", 40),
            limit=scoring.get("digest_max_items", 40))
        print(f"Digest: {path} ({len(digest_jobs)} Treffer über Schwelle)")
    return 0 if status != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
