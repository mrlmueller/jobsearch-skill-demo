"""LinkedIn Guest-Endpoint (kein Login, kein Key) — verifiziert 2026-07-24.

GET /jobs-guest/jobs/api/seeMoreJobPostings/search liefert HTML-Fragmente
mit Job-Cards (10/Seite, Pagination über start=0,10,…). Bewusst sparsam:
wenige Queries, kleine Seitenzahl, 2 s Pause — sonst drosselt LinkedIn.
Volltext gibt es hier nicht (nur Titel/Firma/Ort/Datum) — Relevanz-Urteil
macht der Claude-Layer, Details holt der Nutzer über den Link.
"""
from __future__ import annotations

import html as html_lib
import re
import sys
import time

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
}
PAGE_SIZE = 10
MAX_PAGES = 3           # 30 Treffer/Query reichen (neueste zuerst via f_TPR)
THROTTLE_SECONDS = 2.0

SOURCE = "linkedin"

QUERIES = [
    {"keywords": "Werkstudent Softwareentwicklung", "location": "Ulm"},
    {"keywords": "Werkstudent Software", "location": "Stuttgart"},
    {"keywords": "working student software", "location": "Germany", "f_WT": "2"},  # 2 = Remote
]

CARD_RE = re.compile(
    r'data-entity-urn="urn:li:jobPosting:(?P<id>\d+)".*?'
    r'class="base-card__full-link[^"]*"\s+href="(?P<url>[^"]+)".*?'
    r'class="base-search-card__title[^"]*">\s*(?P<title>.+?)\s*</h3>.*?'
    r'class="base-search-card__subtitle[^"]*">.*?<a[^>]*>\s*(?P<company>.+?)\s*</a>',
    re.DOTALL)
LOCATION_RE = re.compile(r'class="job-search-card__location[^"]*">\s*(.+?)\s*</span>')
TIME_RE = re.compile(r'<time[^>]*datetime="(\d{4}-\d{2}-\d{2})"')


def parse_cards(fragment: str) -> list[dict]:
    jobs = []
    # Card-weise splitten, damit location/time zur richtigen Card gehören
    chunks = re.split(r"(?=data-entity-urn=)", fragment)
    for chunk in chunks:
        m = CARD_RE.search("data-entity-urn=" + chunk if not chunk.startswith("data-entity-urn") else chunk)
        if not m:
            continue
        loc = LOCATION_RE.search(chunk)
        posted = TIME_RE.search(chunk)
        url = html_lib.unescape(m["url"]).split("?")[0]
        jobs.append({
            "job_id": m["id"],
            "title": html_lib.unescape(re.sub(r"\s+", " ", m["title"])).strip(),
            "company": html_lib.unescape(m["company"]).strip(),
            "location": html_lib.unescape(loc.group(1)).strip() if loc else None,
            "posted_at": posted.group(1) if posted else None,
            "url": url,
        })
    return jobs


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 999) or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=3, max=30), reraise=True)
def _fetch_page(query: dict, start: int) -> str:
    time.sleep(THROTTLE_SECONDS)
    r = httpx.get(ENDPOINT, params={**query, "f_TPR": "r604800", "start": start},
                  headers=HEADERS, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.text


def fetch_all(queries: list, fetch_page=None) -> list[dict]:
    fetch = fetch_page or (lambda q, s: _fetch_page(q if isinstance(q, dict) else {"keywords": q}, s))
    seen: set[str] = set()
    jobs: list[dict] = []
    for query in queries:
        try:
            for page in range(MAX_PAGES):
                fragment = fetch(query, page * PAGE_SIZE)
                cards = parse_cards(fragment)
                if not cards:
                    break
                for j in cards:
                    if j["job_id"] not in seen:
                        seen.add(j["job_id"])
                        j["_source"] = SOURCE
                        jobs.append(j)
        except Exception as e:
            print(f"[{SOURCE}] Query {query!r} fehlgeschlagen: {e}", file=sys.stderr)
    return jobs


def fetch() -> list[dict]:
    return fetch_all(QUERIES)


if __name__ == "__main__":
    result = fetch()
    print(f"{len(result)} LinkedIn-Jobs (Guest-Endpoint)")
    for j in result[:15]:
        print(f"- {j['title'][:60]} | {j['company'][:30]} | {j['location']}")
