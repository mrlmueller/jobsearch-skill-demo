"""Verdeckter Markt: Stellen direkt von den ATS-Feeds der Seed-Firmen.

Liest data/companies_seed.csv (ats_type/ats_slug von ats_detect.py gefüllt)
und dispatcht an ats_personio bzw. ats_cleanjson. 'migrated'-Personio-Firmen
werden in der CSV markiert, damit ats_detect sie neu prüft.
"""
from __future__ import annotations

import sys
import time

import ats_cleanjson
import ats_personio
import seed

THROTTLE = 1.0
CLEANJSON_TYPES = set(ats_cleanjson.PROFILES)

SOURCE = "ats"


def fetch_from_rows(rows: list[dict]) -> list[dict]:
    """Reine Fetch-Logik — schreibt NIE selbst auf die Platte.

    'migrated' wird nur in den übergebenen Zeilen markiert; persistieren
    macht ausschließlich fetch(), das die CSV auch selbst geladen hat.
    """
    jobs: list[dict] = []
    for row in rows:
        ats_type = (row.get("ats_type") or "").strip()
        slug = (row.get("ats_slug") or "").strip()
        if not ats_type or not slug:
            continue
        company = row.get("name") or slug
        if ats_type == "personio":
            result = ats_personio.fetch_company(slug, company)
            if result == "migrated":
                row["scrape_status"] = "migrated"
            elif isinstance(result, list):
                jobs.extend(result)
        elif ats_type in CLEANJSON_TYPES:
            jobs.extend(ats_cleanjson.fetch_company(ats_type, slug, company))
        else:
            continue  # z. B. teamtailor: kein Clean-Feed (Phase 3b)
        time.sleep(THROTTLE)
    return jobs


def fetch() -> list[dict]:
    rows = seed.load_rows()
    before = [dict(r) for r in rows]
    jobs = fetch_from_rows(rows)
    if rows != before:  # nur bei echten Markierungen (z. B. migrated) speichern
        try:
            seed.save_rows(rows)
        except Exception as e:
            print(f"[{SOURCE}] CSV-Update fehlgeschlagen: {e}", file=sys.stderr)
    return jobs


if __name__ == "__main__":
    result = fetch()
    print(f"{len(result)} Stellen aus ATS-Feeds")
    for j in result[:20]:
        print(f"- [{j['_source']}] {j['title']} | {j['company']} | {j.get('location')}")
