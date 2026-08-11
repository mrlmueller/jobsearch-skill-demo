"""Arbeitnow Job-Board-API (kein Key). Keine Server-Filter -> client-seitig filtern."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import httpx
import yaml
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
import envutil

ROOT = Path(__file__).parent.parent
ENDPOINT = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 15  # 100 Jobs/Seite; Sicherheitsdeckel

SOURCE = "arbeitnow"

# Rollen-Filter laut Manifest §4.3: title/tags ~ diese Muster
ROLE_PATTERN = re.compile(
    r"werkstudent|working student|junior|software|developer|entwickl|"
    r"automat|full[- ]?stack|devops|backend|frontend|python|typescript",
    re.IGNORECASE,
)


def load_profile() -> dict:
    with open(envutil.profile_path(), encoding="utf-8") as f:
        return yaml.safe_load(f)


def matches_profile(job: dict, regions: list[str]) -> bool:
    """Rolle passt (title/tags/job_types) UND (Ort im Radius ODER remote)."""
    haystack = " ".join(
        [job.get("title") or ""]
        + (job.get("tags") or [])
        + (job.get("job_types") or [])
    )
    if not ROLE_PATTERN.search(haystack):
        return False
    if job.get("remote"):
        return True
    location = (job.get("location") or "").lower()
    return any(r.lower() in location for r in regions)


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _fetch_page(page: int) -> dict:
    # Höflichkeits-Drossel: freie API ("please do not abuse"), sonst 429
    time.sleep(1.5)
    r = httpx.get(ENDPOINT, params={"page": page}, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_all(regions: list[str], fetch_page=_fetch_page) -> list[dict]:
    jobs: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        payload = fetch_page(page)
        data = payload.get("data") or []
        if not data:
            break
        for j in data:
            if matches_profile(j, regions):
                j["_source"] = SOURCE
                jobs.append(j)
        if not (payload.get("links") or {}).get("next"):
            break
    return jobs


def fetch() -> list[dict]:
    profile = load_profile()
    regions = profile["person"]["regions_in_radius"]
    return fetch_all(regions)


if __name__ == "__main__":
    result = fetch()
    print(f"{len(result)} gefilterte Jobs")
    for j in result[:15]:
        loc = "remote" if j.get("remote") else j.get("location")
        print(f"- {j.get('title')} | {j.get('company_name')} | {loc}")
