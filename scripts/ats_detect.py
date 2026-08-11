"""ATS-Detektor: Karriereseite -> (ats_type, ats_slug) -> companies_seed.csv.

Strategie lt. Bauspezifikation §3: Website laden, HTML + finale URL nach
Signatur-Domains durchsuchen; wenn nichts gefunden, Karriere-Links (karriere/
jobs/career/stellen) folgen und dort erneut suchen. Ergebnis wird in die CSV
geschrieben (ats_type, ats_slug, ats_feed_url) — beim nächsten Lauf holen die
Adapter die Stellen dann direkt, ohne erneute Detektion.

Aufruf: python scripts/ats_detect.py [limit]
"""
from __future__ import annotations

import re
import sys
import time
from datetime import date
from urllib.parse import urljoin

import httpx

import seed

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "de-DE,de;q=0.9"}
THROTTLE = 1.0
MAX_CAREER_LINKS = 3
NOT_SLUGS = {"www", "boards", "jobs", "api", "careers", "app", "embed"}

# Reihenfolge = Priorität (Personio zuerst: DACH-KMU-Standard)
SIGNATURES = [
    ("personio", re.compile(r"https?://([\w-]+)\.jobs\.personio\.(?:de|com)", re.I)),
    ("greenhouse", re.compile(
        r"boards(?:-api)?\.greenhouse\.io/(?:embed/job_board\?for=|v1/boards/)?([\w-]+)", re.I)),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([\w-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([\w-]+)", re.I)),
    ("recruitee", re.compile(r"https?://([\w-]+)\.recruitee\.com", re.I)),
    ("smartrecruiters", re.compile(
        r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)", re.I)),
    ("workday", re.compile(
        r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[\w-]{2,5}/)?([\w-]+)", re.I)),
    ("teamtailor", re.compile(r"https?://([\w-]+)\.teamtailor\.com", re.I)),
]

CAREER_WORDS = re.compile(r"karriere|career|jobs|stellen|join", re.I)
HREF_RE = re.compile(r'href="([^"]+)"', re.I)


def detect_from_text(text: str) -> tuple[str, str] | None:
    for ats_type, pattern in SIGNATURES:
        for m in pattern.finditer(text):
            if ats_type == "workday":
                tenant, dc, site = m.group(1), m.group(2), m.group(3)
                if tenant.lower() in NOT_SLUGS:
                    continue
                return ats_type, f"{tenant}.{dc}/{site}"
            slug = m.group(1)
            if slug.lower() in NOT_SLUGS:
                continue
            return ats_type, slug
    return None


def career_links(html: str, base_url: str) -> list[str]:
    links = []
    for href in HREF_RE.findall(html):
        if CAREER_WORDS.search(href) and "impressum" not in href.lower():
            links.append(urljoin(base_url, href))
    # Duplikate raus, Reihenfolge stabil
    unique = list(dict.fromkeys(links))
    return unique[:MAX_CAREER_LINKS]


def feed_url_for(ats_type: str, slug: str) -> str:
    if ats_type == "personio":
        return f"https://{slug}.jobs.personio.de/xml"
    if ats_type == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    if ats_type == "lever":
        return f"https://api.lever.co/v0/postings/{slug}?mode=json"
    if ats_type == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    if ats_type == "recruitee":
        return f"https://{slug}.recruitee.com/api/offers/"
    if ats_type == "smartrecruiters":
        return f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset=0"
    if ats_type == "workday":
        tenant_dc, site = slug.split("/", 1)
        tenant = tenant_dc.split(".")[0]
        return f"https://{tenant_dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    return ""  # teamtailor: kein Clean-Feed, JSON-LD-Fallback (Phase 3b)


def _get(url: str) -> httpx.Response | None:
    try:
        return httpx.get(url, headers=UA, timeout=15, follow_redirects=True)
    except Exception:
        return None


def detect_company(website: str) -> tuple[str, str] | None:
    """Website laden, Signaturen suchen; sonst Karriere-Links folgen."""
    r = _get(website)
    if r is None:
        return None
    found = detect_from_text(str(r.url) + " " + r.text)
    if found:
        return found
    for link in career_links(r.text, base_url=str(r.url)):
        time.sleep(THROTTLE / 2)
        sub = _get(link)
        if sub is None:
            continue
        found = detect_from_text(str(sub.url) + " " + sub.text)
        if found:
            return found
    return None


def main(argv: list[str]) -> int:
    limit = int(argv[0]) if argv else 10_000
    rows = seed.load_rows()
    todo = [r for r in rows
            if (r.get("website") or "").strip()
            and not (r.get("ats_type") or "").strip()
            and (r.get("scrape_status") or "") != "ats_none"][:limit]
    print(f"{len(todo)} Firmen zu prüfen …", file=sys.stderr)
    hits = 0
    today = date.today().isoformat()
    for i, row in enumerate(todo, 1):
        time.sleep(THROTTLE)
        found = detect_company(row["website"])
        if found:
            ats_type, slug = found
            row["ats_type"], row["ats_slug"] = ats_type, slug
            row["ats_feed_url"] = feed_url_for(ats_type, slug)
            row["last_verified"] = today
            row["scrape_status"] = "ok"
            hits += 1
            print(f"[{i}/{len(todo)}] {row['name']}: {ats_type} ({slug})")
        else:
            row["scrape_status"] = "ats_none"  # geprüft, nichts gefunden
    seed.save_rows(rows)
    print(f"\n{hits} ATS erkannt bei {len(todo)} geprüften Firmen. CSV aktualisiert.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
