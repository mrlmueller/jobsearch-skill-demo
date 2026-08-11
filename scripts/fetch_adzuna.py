"""Adzuna-API (app_id/app_key aus .env). Aggregiert u. a. Indeed/Stepstone.

Liefert nur Snippets; Volltext-Beurteilung übernimmt der Claude-Layer beim
Digest. Ohne Credentials wirft fetch() MissingCredentials — run.py
überspringt die Quelle dann sauber.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

import envutil

ROOT = Path(__file__).parent.parent
ENDPOINT = "https://api.adzuna.com/v1/api/jobs/de/search/{page}"
MAX_PAGES = 5  # 50/Seite; Free-Tier schonen

SOURCE = "adzuna"

PARAMS = {
    "what_or": "werkstudent junior softwareentwickler fullstack automatisierung",
    "what_exclude": "senior lead principal",
    "where": "Ulm",
    "distance": 100,
    "category": "it-jobs",
    "part_time": 1,
    "results_per_page": 50,
    "sort_by": "date",
}


class MissingCredentials(RuntimeError):
    pass


def _credentials() -> tuple[str | None, str | None]:
    envutil.load_env()
    return os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")


def has_credentials() -> bool:
    app_id, app_key = _credentials()
    return bool(app_id and app_key)


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _fetch_page(page: int) -> dict:
    app_id, app_key = _credentials()
    r = httpx.get(ENDPOINT.format(page=page),
                  params={**PARAMS, "app_id": app_id, "app_key": app_key},
                  timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_all(fetch_page=_fetch_page) -> list[dict]:
    jobs: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        payload = fetch_page(page)
        results = payload.get("results") or []
        if not results:
            break
        for j in results:
            j["_source"] = SOURCE
            jobs.append(j)
        if len(results) < PARAMS["results_per_page"]:
            break
    return jobs


def fetch() -> list[dict]:
    if not has_credentials():
        raise MissingCredentials(
            "ADZUNA_APP_ID/ADZUNA_APP_KEY fehlen in .env — Quelle wird übersprungen")
    return fetch_all()


if __name__ == "__main__":
    if not has_credentials():
        print("Keine Adzuna-Credentials in .env — nichts zu tun.")
        sys.exit(0)
    result = fetch()
    print(f"{len(result)} Adzuna-Jobs")
    for j in result[:10]:
        print(f"- {j.get('title')} | {(j.get('company') or {}).get('display_name')} "
              f"| {(j.get('location') or {}).get('display_name')}")
