"""Portal-Parser + Ingest — die Fetch-Arbeit macht CLAUDE (Firecrawl-MCP).

Arbeitsteilung (Entscheidung 2026-07-23, keine API-Keys):
  1. Claude scrapt die Portal-URLs per Firecrawl-MCP als Markdown
     (`python scripts/scrape_portals.py list` zeigt Portale + URLs).
  2. Claude speichert das Markdown als Datei (z. B. data/runs/<datum>_<portal>.md).
  3. `python scripts/scrape_portals.py ingest <portal> <datei>` parst
     deterministisch, filtert, bewertet und upsertet in seen.sqlite.

Die Parser sind gegen echte Ausschnitte getestet (tests/test_scrape_portals.py).
Markdown-Format = 1 Firecrawl-Credit/Seite; json-Format (5 Credits) wird
bewusst nicht genutzt.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fetch_arbeitnow import ROLE_PATTERN

ROOT = Path(__file__).parent.parent

# Rausch-Zeilen der Portale (Badges, Icons), die zwischen den Feldern stehen
NOISE = {"Karte Indikator", "Haus", "Stoppuhr", "Schnelle Rückmeldung", "Blitz",
         "Wenig Konkurrenz", "Empfehlung", "Sofort-Bewerbung", "Aktualisiert"}

HEADER_RE = re.compile(r"\[### (?P<title>.+?)\]\((?P<url>https?://[^\s)\"]+)")
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


def _clean_lines(markdown: str) -> list[str]:
    """Zeilen entstacken (Bullet-Einrückung weg), Bilder/Noise raus."""
    lines = []
    for line in markdown.splitlines():
        line = line.strip().lstrip("*").strip().replace("\\+", "+")
        if not line or line.startswith("!["):
            continue
        lines.append(line)
    return lines


def parse_werkstudenten_jobs(markdown: str) -> list[dict]:
    """### [Titel](url) / Datum | / Firma | / Ort | / Arbeitszeit / Snippet."""
    jobs = []
    lines = _clean_lines(markdown)
    for i, line in enumerate(lines):
        m = re.match(r"### \[(?P<title>.+?)\]\((?P<url>https://www\.werkstudenten-jobs\.de/job[^\s)\"]+)", line)
        if not m:
            continue
        fields = [l.rstrip(" |") for l in lines[i + 1:i + 5]]
        job = {"title": m["title"], "url": m["url"],
               "posted_date": fields[0] if fields and DATE_RE.match(fields[0]) else None,
               "company": fields[1] if len(fields) > 1 else None,
               "location": fields[2] if len(fields) > 2 else None,
               "homeoffice": "homeoffice" in (fields[3].lower() if len(fields) > 3 else ""),
               "salary": None,
               "snippet": lines[i + 5] if len(lines) > i + 5 else ""}
        jobs.append(job)
    return jobs


def parse_campusjaeger(markdown: str) -> list[dict]:
    """[### Titel](/job/…) / Firma / Ort / [Homeoffice] / [h pro Woche] / [€]."""
    jobs = []
    lines = _clean_lines(markdown)
    starts = [i for i, l in enumerate(lines)
              if re.match(r"\[### .+\]\(https://www\.campusjaeger\.de/job/", l)]
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        m = HEADER_RE.match(lines[i])
        block = [l for l in lines[i + 1:end] if l not in NOISE]
        job = {"title": m["title"], "url": m["url"], "company": None,
               "location": None, "homeoffice": False, "salary": None,
               "posted_date": None, "snippet": ""}
        rest = []
        for l in block:
            if l == "Homeoffice möglich":
                job["homeoffice"] = True
            elif re.search(r"€ pro Stunde", l):
                job["salary"] = l
            elif re.search(r"h pro Woche", l):
                continue
            elif l.startswith("[") or l.startswith("#"):
                continue
            else:
                rest.append(l)
        if rest:
            job["company"] = rest[0]
        if len(rest) > 1:
            job["location"] = rest[1]
        if len(rest) > 2:
            job["snippet"] = rest[-1]
        jobs.append(job)
    return jobs


def parse_meinestadt(markdown: str) -> list[dict]:
    """[### Titel](url) / Firma / Ort / Datum / Skill-Tags…"""
    jobs = []
    lines = _clean_lines(markdown)
    starts = [i for i, l in enumerate(lines)
              if HEADER_RE.match(l) and ("meinestadt.de" in l)]
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        m = HEADER_RE.match(lines[i])
        block = [l for l in lines[i + 1:end]
                 if l not in NOISE and not l.startswith("[") and not l.startswith("#")]
        job = {"title": m["title"], "url": m["url"],
               "company": block[0] if block else None,
               "location": block[1] if len(block) > 1 else None,
               "posted_date": next((l for l in block if DATE_RE.match(l)), None),
               "homeoffice": any("homeoffice" in l.lower() for l in block),
               "salary": next((l for l in block if "€" in l), None),
               "snippet": " ".join(block[3:15])}
        jobs.append(job)
    return jobs


def parse_stepstone(markdown: str) -> list[dict]:
    """[Titel](stellenangebote--…) / ----- / Firma / Ort / Snippet."""
    jobs = []
    lines = [l for l in _clean_lines(markdown) if not re.match(r"^-{5,}$", l)]
    starts = [i for i, l in enumerate(lines)
              if re.match(r"\[.+\]\(https://www\.stepstone\.de/stellenangebote--", l)]
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        m = re.match(r"\[(?P<title>.+?)\]\((?P<url>[^)]+)\)", lines[i])
        block = [l for l in lines[i + 1:end]
                 if l not in NOISE and not l.startswith("[") and not l.startswith("#")]
        location = block[1] if len(block) > 1 else None
        jobs.append({
            "title": m["title"], "url": m["url"],
            "company": block[0] if block else None,
            "location": location,
            "posted_date": None,
            "homeoffice": "home-office" in (location or "").lower()
                          or "homeoffice" in (location or "").lower(),
            "salary": None,
            "snippet": " ".join(block[2:6]),
        })
    return jobs


_MEGALINK_RE = re.compile(
    r"\[!\[[^\]]*\]\([^)]*\)(?P<body>.*?)\]\((?P<url>%s[^)\s]+)\)",
    re.DOTALL)


def _parse_megalink_cards(markdown: str, url_prefix: str,
                          fields: str) -> list[dict]:
    """Portale, deren ganze Job-Card EIN Markdown-Link ist (Absolventa, get-in-IT).

    fields: 'title_first' (Absolventa: Titel/-----/Firma/…) oder
            'company_first' (get-in-IT: [Tipp]/Firma/Titel/Kategorie/Ort/…).
    """
    jobs = []
    pattern = re.compile(_MEGALINK_RE.pattern % re.escape(url_prefix), re.DOTALL)
    for m in pattern.finditer(markdown):
        lines = [l.strip().lstrip("*").strip().rstrip("\\").strip()
                 for l in m["body"].replace("\\\n", "\n").splitlines()]
        lines = [l for l in lines
                 if l and not re.match(r"^-{4,}$", l) and l not in ("Tipp", "Neu")]
        # doppelte Titel-Zeilen (Absolventa wiederholt den Titel) einmalig halten
        seen_lines: list[str] = []
        for l in lines:
            if l not in seen_lines:
                seen_lines.append(l)
        homeoffice = any("home-office" in l.lower() or "homeoffice" in l.lower()
                         for l in seen_lines)
        content = [l for l in seen_lines
                   if not ("home-office" in l.lower() or "homeoffice" in l.lower())]
        location = next((l.replace("Standort", "").strip() for l in content
                         if l.startswith("Standort")), None)
        content = [l for l in content if not l.startswith("Standort")]
        if fields == "title_first":
            title = content[0] if content else None
            company = content[1] if len(content) > 1 else None
        else:  # company_first
            company = content[0] if content else None
            title = content[1] if len(content) > 1 else None
            if location is None and len(content) > 3:
                location = content[3]
        jobs.append({"title": title, "company": company, "location": location,
                     "url": m["url"], "posted_date": None,
                     "homeoffice": homeoffice, "salary": None, "snippet": ""})
    return jobs


def parse_absolventa(markdown: str) -> list[dict]:
    return _parse_megalink_cards(
        markdown, "https://www.absolventa.de/stellenangebote/", "title_first")


def parse_get_in_it(markdown: str) -> list[dict]:
    return _parse_megalink_cards(
        markdown, "https://www.get-in-it.de/jobsuche/p", "company_first")


PORTALS = {
    # name -> (url, parser). URLs verifiziert 2026-07-23/24, s. config/sources.yaml
    "werkstudenten_jobs": ("https://www.werkstudenten-jobs.de/werkstudent/software",
                           parse_werkstudenten_jobs),
    "campusjaeger": ("https://www.campusjaeger.de/werkstudent/softwareentwicklung",
                     parse_campusjaeger),
    "meinestadt": ("https://jobs.meinestadt.de/ulm/studentenjobs",
                   parse_meinestadt),
    # StepStone braucht Firecrawl proxy:"auto" (Anti-Bot), verifiziert 2026-07-24
    "stepstone": ("https://www.stepstone.de/jobs/werkstudent-softwareentwicklung/in-ulm?radius=100",
                  parse_stepstone),
    "absolventa": ("https://www.absolventa.de/werkstudentenjobs/stadt/ulm",
                   parse_absolventa),
    # get-in-IT: URL-Ortsfilter greift nicht -> bundesweite Liste, Radius/Remote
    # filtert score.py; viele Einträge mit Home-Office-Flag
    "get_in_it": ("https://www.get-in-it.de/jobsuche", parse_get_in_it),
}

# Nur via Playwright renderbar (JS-Apps) -> Claude extrahiert selbst und nutzt
# `ingest-json <name> <datei>`. Verifiziert 2026-07-24.
PLAYWRIGHT_SOURCES = {
    "indeed": "https://de.indeed.com/jobs?q=werkstudent+software&l=Ulm&radius=50&fromage=14",
    "germantechjobs": "https://germantechjobs.de/jobs/all/Ulm",
    "thu_jobportal": "https://www.jobportal-ulm.de/hsulcc/",
    "hnu_jobboerse": "https://jobboerse.hnu.de/jobs",
}


def filter_jobs(jobs: list[dict], portal: str = "meinestadt") -> list[dict]:
    """Rollen-Filter (Recall-orientiert) + Quelle taggen."""
    kept = []
    for j in jobs:
        haystack = f"{j.get('title') or ''} {j.get('snippet') or ''}"
        if ROLE_PATTERN.search(haystack):
            j["_source"] = f"portal_{portal}"
            kept.append(j)
    return kept


def _pipe_and_upsert(conn, parsed: list[dict], portal: str) -> dict:
    import dedup
    import normalize
    import score
    import store

    kept = filter_jobs(parsed, portal=portal)
    jobs = score.score_all(dedup.dedup_all(normalize.normalize_all(kept)))
    new = sum(1 for j in jobs if store.upsert(conn, j))
    return {"parsed": len(parsed), "kept": len(kept),
            "new": new, "seen": len(jobs) - new}


def ingest_markdown(conn, portal: str, markdown: str) -> dict:
    """Markdown (von Claude gescrapt) -> parse -> filter -> score -> upsert."""
    _, parser = PORTALS[portal]  # KeyError bei unbekanntem Portal = gewollt
    return _pipe_and_upsert(conn, parser(markdown), portal)


def ingest_json(conn, portal: str, jobs: list[dict]) -> dict:
    """Für Quellen ohne deterministischen Parser: Claude extrahiert selbst
    (z. B. Indeed via Playwright) und übergibt eine Liste von Dicts mit
    title, company, location, url [, posted_date, homeoffice, salary, snippet]."""
    return _pipe_and_upsert(conn, jobs, portal)


def main(argv: list[str]) -> int:
    import store

    if len(argv) >= 1 and argv[0] == "list":
        for name, (url, _) in PORTALS.items():
            print(f"markdown\t{name}\t{url}")
        for name, url in PLAYWRIGHT_SOURCES.items():
            print(f"playwright\t{name}\t{url}")
        return 0
    if len(argv) >= 3 and argv[0] in ("ingest", "ingest-json"):
        import json as json_lib
        portal, path = argv[1], Path(argv[2])
        conn = store.init_db()
        if argv[0] == "ingest":
            stats = ingest_markdown(conn, portal, path.read_text(encoding="utf-8"))
        else:
            stats = ingest_json(conn, portal,
                                json_lib.loads(path.read_text(encoding="utf-8")))
        print(f"[portal_{portal}] {stats['parsed']} geparst -> {stats['kept']} relevant "
              f"-> {stats['new']} neu, {stats['seen']} bekannt")
        return 0
    print("Nutzung: scrape_portals.py list | ingest <portal> <md-datei> | "
          "ingest-json <name> <json-datei>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
