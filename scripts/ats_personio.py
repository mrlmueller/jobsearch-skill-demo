"""Personio-ATS-Adapter (DACH-KMU-Standard, kein Key).

Endpoint: https://{slug}.jobs.personio.de/xml  (XML, Volltext in CDATA).
307 = Firma auf personio.com migriert -> als 'migrated' melden, damit
ats_detect den Eintrag neu prüfen kann. Verifizierte Felder lt.
Bauspezifikation §3: id, name, office, department, employmentType,
schedule, seniority, createdAt, jobDescriptions[].
"""
from __future__ import annotations

import sys
import time
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET  # fremdes XML: schützt vor XXE/Entity-Bomben
import httpx

from normalize import strip_html

FEED_URL = "https://{slug}.jobs.personio.de/xml"
JOB_URL = "https://{slug}.jobs.personio.de/job/{id}"
UA = {"User-Agent": "Mozilla/5.0 (jobsearch-skill; personal use)"}
THROTTLE = 1.0

SOURCE = "ats_personio"


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def parse_xml(xml_text: str, slug: str, company: str) -> list[dict]:
    jobs = []
    root = ET.fromstring(xml_text)
    for pos in root.iter("position"):
        job_id = _text(pos, "id")
        descriptions = []
        for jd in pos.iter("jobDescription"):
            name = _text(jd, "name")
            value = strip_html(_text(jd, "value"))
            if value:
                descriptions.append(f"{name}: {value}" if name else value)
        created = _text(pos, "createdAt")
        jobs.append({
            "_source": SOURCE,
            "job_id": job_id,
            "title": _text(pos, "name"),
            "company": company,
            "location": _text(pos, "office"),
            "department": _text(pos, "department"),
            "employment_hint": _text(pos, "employmentType"),
            "schedule": _text(pos, "schedule"),
            "seniority": _text(pos, "seniority"),
            "keywords": _text(pos, "keywords"),
            "posted_at": created[:10] if created else None,
            "description": "\n".join(descriptions),
            "url": JOB_URL.format(slug=slug, id=job_id),
        })
    return jobs


def fetch_company(slug: str, company: str):
    """Liste Roh-Jobs ODER 'migrated' (307) ODER 'gone' (404/Fehler)."""
    try:
        r = httpx.get(FEED_URL.format(slug=slug), headers=UA, timeout=30)
    except httpx.TransportError as e:
        print(f"[{SOURCE}] {slug}: {e}", file=sys.stderr)
        return "gone"
    if r.status_code == 307:
        return "migrated"
    if r.status_code != 200:
        return "gone"
    try:
        return parse_xml(r.text, slug=slug, company=company)
    except (ParseError, ValueError) as e:
        print(f"[{SOURCE}] {slug}: XML-Fehler {e}", file=sys.stderr)
        return "gone"


def fetch_many(companies: list[tuple[str, str]]) -> list[dict]:
    """[(slug, firmenname), …] -> Roh-Jobs aller erreichbaren Feeds."""
    jobs: list[dict] = []
    for slug, company in companies:
        result = fetch_company(slug, company)
        if isinstance(result, list):
            jobs.extend(result)
        else:
            print(f"[{SOURCE}] {slug}: {result}", file=sys.stderr)
        time.sleep(THROTTLE)
    return jobs


if __name__ == "__main__":
    # Schnelltest: python scripts/ats_personio.py <slug> [firmenname]
    slug = sys.argv[1] if len(sys.argv) > 1 else "demo"
    company = sys.argv[2] if len(sys.argv) > 2 else slug
    result = fetch_company(slug, company)
    if isinstance(result, str):
        print(f"{slug}: {result}")
    else:
        print(f"{slug}: {len(result)} Stellen")
        for j in result[:10]:
            print(f"- {j['title']} | {j['location']} | {j['schedule']}")
