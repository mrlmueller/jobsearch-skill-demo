"""Remote-Job-APIs ohne Key: Himalayas + Jobicy (Phase 2)."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import yaml
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from fetch_arbeitnow import ROLE_PATTERN

ROOT = Path(__file__).parent.parent

HIMALAYAS_ENDPOINT = "https://himalayas.app/jobs/api/search"
JOBICY_ENDPOINT = "https://jobicy.com/api/v2/remote-jobs"
REMOTEOK_ENDPOINT = "https://remoteok.com/api"
REMOTIVE_ENDPOINT = "https://remotive.com/api/remote-jobs"

# locationRestrictions leer = weltweit; sonst muss DE/Europa dabei sein
ALLOWED_LOCATIONS = ("germany", "europe", "european union", "emea", "dach")
# für Quellen, die "Worldwide"/"Anywhere" explizit ausschreiben
ALLOWED_OR_WORLDWIDE = ALLOWED_LOCATIONS + ("worldwide", "anywhere", "remote")

HIMALAYAS_QUERIES = ["working student", "junior software engineer",
                     "junior developer", "automation engineer"]


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


def himalayas_ok(job: dict) -> bool:
    if not ROLE_PATTERN.search(job.get("title") or ""):
        return False
    restrictions = [r.lower() for r in (job.get("locationRestrictions") or [])]
    if not restrictions:
        return True
    return any(a in r for r in restrictions for a in ALLOWED_LOCATIONS)


def jobicy_ok(job: dict) -> bool:
    # geo=germany filtert die API bereits; hier nur Rollen-Check
    haystack = f"{job.get('jobTitle') or ''} {job.get('jobIndustry') or ''}"
    return bool(ROLE_PATTERN.search(haystack))


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _fetch_himalayas_query(query: str) -> dict:
    # Hinweis: 'sort=dateDesc' aus sources.yaml ist ungültig geworden (400 "Invalid sort")
    r = httpx.get(HIMALAYAS_ENDPOINT, params={"q": query, "limit": 50},
                  timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def fetch_himalayas(queries: list[str] | None = None,
                    fetch_query=_fetch_himalayas_query) -> list[dict]:
    seen: set[str] = set()
    jobs: list[dict] = []
    for query in queries or HIMALAYAS_QUERIES:
        try:
            payload = fetch_query(query)
        except Exception as e:
            print(f"[himalayas] Query '{query}' fehlgeschlagen: {e}", file=sys.stderr)
            continue
        for j in payload.get("jobs") or []:
            guid = j.get("guid") or j.get("applicationLink")
            if guid and guid not in seen and himalayas_ok(j):
                seen.add(guid)
                j["_source"] = "himalayas"
                jobs.append(j)
    return jobs


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _fetch_jobicy() -> dict:
    r = httpx.get(JOBICY_ENDPOINT, params={"count": 50, "industry": "dev",
                                           "geo": "germany"},
                  timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def fetch_jobicy(fetch_fn=_fetch_jobicy) -> list[dict]:
    try:
        payload = fetch_fn()
    except Exception as e:
        print(f"[jobicy] fehlgeschlagen: {e}", file=sys.stderr)
        return []
    jobs = []
    for j in payload.get("jobs") or []:
        if jobicy_ok(j):
            j["_source"] = "jobicy"
            jobs.append(j)
    return jobs


def remoteok_ok(job: dict) -> bool:
    haystack = f"{job.get('position') or ''} " + " ".join(job.get("tags") or [])
    if not ROLE_PATTERN.search(haystack):
        return False
    location = (job.get("location") or "").lower()
    if not location:
        return True
    return any(a in location for a in ALLOWED_OR_WORLDWIDE)


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _fetch_remoteok() -> list:
    r = httpx.get(REMOTEOK_ENDPOINT, timeout=30, follow_redirects=True,
                  headers={"User-Agent": "jobsearch-skill (personal use)"})
    r.raise_for_status()
    return r.json()


def fetch_remoteok(fetch_fn=_fetch_remoteok) -> list[dict]:
    try:
        payload = fetch_fn()
    except Exception as e:
        print(f"[remoteok] fehlgeschlagen: {e}", file=sys.stderr)
        return []
    jobs = []
    for j in payload:
        if "position" not in j:  # erster Eintrag ist der Legal-Hinweis
            continue
        if remoteok_ok(j):
            j["_source"] = "remoteok"
            jobs.append(j)
    return jobs


def remotive_ok(job: dict) -> bool:
    haystack = f"{job.get('title') or ''} " + " ".join(job.get("tags") or [])
    if not ROLE_PATTERN.search(haystack):
        return False
    location = (job.get("candidate_required_location") or "").lower()
    if not location:
        return True
    return any(a in location for a in ALLOWED_OR_WORLDWIDE)


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _fetch_remotive() -> dict:
    r = httpx.get(REMOTIVE_ENDPOINT,
                  params={"category": "software-dev", "limit": 100},
                  timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def fetch_remotive(fetch_fn=_fetch_remotive) -> list[dict]:
    try:
        payload = fetch_fn()
    except Exception as e:
        print(f"[remotive] fehlgeschlagen: {e}", file=sys.stderr)
        return []
    jobs = []
    for j in payload.get("jobs") or []:
        if remotive_ok(j):
            j["_source"] = "remotive"
            jobs.append(j)
    return jobs


def fetch() -> list[dict]:
    return fetch_himalayas() + fetch_jobicy() + fetch_remoteok() + fetch_remotive()


if __name__ == "__main__":
    result = fetch()
    print(f"{len(result)} Remote-Jobs (himalayas + jobicy)")
    for j in result[:15]:
        title = j.get("title") or j.get("jobTitle")
        company = j.get("companyName")
        print(f"- [{j['_source']}] {title} | {company}")
