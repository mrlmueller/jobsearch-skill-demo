"""Arbeitsagentur Jobsuche-API (kein Key). Pro Titel-Synonym eine Query, paginiert."""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import httpx
import yaml
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
import envutil

ROOT = Path(__file__).parent.parent
BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
SEARCH = BASE + "/pc/v4/app/jobs"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}
PAGE_SIZE = 100
MAX_PAGES = 10  # Sicherheitsdeckel pro Synonym

SOURCE = "arbeitsagentur"
JOB_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"


def load_profile() -> dict:
    with open(envutil.profile_path(), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _fetch_page(synonym: str, page: int) -> list[dict]:
    r = httpx.get(
        SEARCH,
        params={"was": synonym, "wo": "Ulm", "umkreis": 100,
                "arbeitszeit": "tz;ho", "veroeffentlichtseit": 14,
                "size": PAGE_SIZE, "page": page},
        headers=HEADERS, timeout=30,
    )
    r.raise_for_status()
    return r.json().get("stellenangebote") or []


def fetch_all(synonyms: list[str], fetch_page=_fetch_page) -> list[dict]:
    """Alle Synonyme abfragen, paginieren bis leer, refnr-dedupliziert."""
    seen: set[str] = set()
    jobs: list[dict] = []
    failures = 0
    for synonym in synonyms:
        try:
            for page in range(1, MAX_PAGES + 1):
                batch = fetch_page(synonym, page)
                if not batch:
                    break
                for j in batch:
                    refnr = j.get("refnr")
                    if refnr and refnr not in seen:
                        seen.add(refnr)
                        j["_source"] = SOURCE
                        j["_url"] = JOB_URL.format(refnr=refnr)
                        j["_query"] = synonym
                        jobs.append(j)
                if len(batch) < PAGE_SIZE:
                    break
        except Exception as e:  # ein Synonym darf die anderen nicht abbrechen
            failures += 1
            print(f"[{SOURCE}] Synonym '{synonym}' fehlgeschlagen: {e}", file=sys.stderr)
    if failures and failures == len(synonyms):
        # Scheitern ALLE Queries, ist die Quelle als Ganzes ausgefallen und
        # soll im Lauf als fehlgeschlagen zählen, nicht als "ok mit 0 Jobs".
        raise RuntimeError(f"alle {failures} Synonym-Queries fehlgeschlagen")
    return jobs


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _fetch_detail(refnr: str) -> dict:
    enc = base64.b64encode(refnr.encode()).decode()
    r = httpx.get(f"{BASE}/pc/v4/jobdetails/{enc}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def enrich_with_details(jobs: list[dict], fetch_detail=_fetch_detail) -> None:
    """Volltext + Homeoffice-Flag je Job nachladen (Feld: stellenangebotsBeschreibung)."""
    for job in jobs:
        description, homeoffice = "", False
        try:
            detail = fetch_detail(job.get("refnr") or "")
            description = detail.get("stellenangebotsBeschreibung") or ""
            homeoffice = bool(detail.get("homeofficemoeglich"))
        except Exception as e:
            print(f"[{SOURCE}] Detail {job.get('refnr')} fehlgeschlagen: {e}",
                  file=sys.stderr)
        job["_description"] = description
        job["_homeoffice"] = homeoffice


def fetch() -> list[dict]:
    profile = load_profile()
    synonyms = (profile.get("target_titles_de") or []) + (profile.get("target_titles_en") or [])
    jobs = fetch_all(synonyms)
    enrich_with_details(jobs)
    return jobs


if __name__ == "__main__":
    result = fetch()
    print(f"{len(result)} Roh-Jobs (refnr-dedupliziert)")
    for j in result[:10]:
        ort = (j.get("arbeitsort") or {}).get("ort")
        print(f"- {j.get('titel')} | {j.get('arbeitgeber')} | {ort}")
