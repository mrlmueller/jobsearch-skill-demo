"""Ein Basis-Adapter für sechs Clean-JSON-ATS (Bauspezifikation §3).

Alle Endpoints sind unauthentifiziert und slug-parametrisiert; nur
URL-Template und Feld-Mapping unterscheiden sich -> ein parse() mit
Profil-Registry. Workday ist POST, alle anderen GET.
"""
from __future__ import annotations

import html as html_lib
import sys
import time
from datetime import datetime, timezone

import httpx

from ats_detect import feed_url_for
from normalize import strip_html

UA = {"User-Agent": "Mozilla/5.0 (jobsearch-skill; personal use)"}
THROTTLE = 1.0


def _iso(value) -> str | None:
    if not value:
        return None
    if isinstance(value, (int, float)):          # Lever: Millisekunden-Epoch
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
    return str(value)[:10].replace(" ", "") or None


def _greenhouse(payload, company, slug):
    for j in payload.get("jobs") or []:
        yield {
            "job_id": str(j.get("id")),
            "title": j.get("title"),
            "location": (j.get("location") or {}).get("name"),
            "url": j.get("absolute_url"),
            "posted_at": _iso(j.get("updated_at")),
            "description": strip_html(html_lib.unescape(j.get("content") or "")),
        }


def _lever(payload, company, slug):
    for j in payload or []:
        cats = j.get("categories") or {}
        yield {
            "job_id": str(j.get("id")),
            "title": j.get("text"),
            "location": cats.get("location"),
            "employment_hint": cats.get("commitment"),
            "url": j.get("hostedUrl"),
            "posted_at": _iso(j.get("createdAt")),
            "description": j.get("descriptionPlain") or strip_html(j.get("description") or ""),
        }


def _ashby(payload, company, slug):
    for j in payload.get("jobs") or []:
        yield {
            "job_id": str(j.get("id")),
            "title": j.get("title"),
            "location": j.get("location"),
            "employment_hint": j.get("employmentType"),
            "url": j.get("jobUrl") or j.get("applyUrl"),
            "posted_at": _iso(j.get("publishedAt")),
            "description": strip_html(j.get("descriptionHtml") or ""),
        }


def _recruitee(payload, company, slug):
    for j in payload.get("offers") or []:
        yield {
            "job_id": str(j.get("id")),
            "title": j.get("title"),
            "location": j.get("location"),
            "employment_hint": j.get("employment_type_code"),
            "url": j.get("careers_url"),
            "posted_at": _iso(j.get("created_at")),
            "description": strip_html(j.get("description") or ""),
        }


def _smartrecruiters(payload, company, slug):
    for j in payload.get("content") or []:
        loc = j.get("location") or {}
        yield {
            "job_id": str(j.get("id")),
            "title": j.get("name"),
            "location": loc.get("city") or loc.get("country"),
            "url": j.get("applyUrl") or j.get("ref"),
            "posted_at": _iso(j.get("releasedDate")),
            "description": "",  # Volltext nur per Detail-Call; enrich.py übernimmt
        }


def _workday(payload, company, slug):
    tenant_dc, site = (slug or "x.wd1/site").split("/", 1)
    base = f"https://{tenant_dc}.myworkdayjobs.com/de-DE/{site}"
    for j in payload.get("jobPostings") or []:
        bullets = j.get("bulletFields") or []
        yield {
            "job_id": bullets[0] if bullets else j.get("externalPath"),
            "title": j.get("title"),
            "location": j.get("locationsText"),
            "url": base + (j.get("externalPath") or ""),
            "posted_at": None,  # Workday liefert nur "Vor N Tagen gepostet"
            "description": "",
        }


PROFILES = {
    "greenhouse": _greenhouse,
    "lever": _lever,
    "ashby": _ashby,
    "recruitee": _recruitee,
    "smartrecruiters": _smartrecruiters,
    "workday": _workday,
}


def parse(ats_type: str, payload, company: str, slug: str = "") -> list[dict]:
    mapper = PROFILES[ats_type]  # KeyError bei unbekanntem Profil = gewollt
    jobs = []
    for j in mapper(payload, company, slug):
        j["_source"] = f"ats_{ats_type}"
        j["company"] = company
        jobs.append(j)
    return jobs


def fetch_company(ats_type: str, slug: str, company: str) -> list[dict]:
    url = feed_url_for(ats_type, slug)
    if not url:
        return []
    try:
        if ats_type == "workday":
            r = httpx.post(url, json={"limit": 20, "offset": 0},
                           headers={**UA, "Content-Type": "application/json"},
                           timeout=30)
        else:
            r = httpx.get(url, headers=UA, timeout=30, follow_redirects=True)
        r.raise_for_status()
        return parse(ats_type, r.json(), company=company, slug=slug)
    except Exception as e:
        print(f"[ats_{ats_type}] {slug}: {e}", file=sys.stderr)
        return []


def fetch_many(companies: list[tuple[str, str, str]]) -> list[dict]:
    """[(ats_type, slug, firmenname), …] -> Roh-Jobs aller Feeds."""
    jobs: list[dict] = []
    for ats_type, slug, company in companies:
        jobs.extend(fetch_company(ats_type, slug, company))
        time.sleep(THROTTLE)
    return jobs


if __name__ == "__main__":
    # Schnelltest: python scripts/ats_cleanjson.py <typ> <slug> [firma]
    ats_type, slug = sys.argv[1], sys.argv[2]
    company = sys.argv[3] if len(sys.argv) > 3 else slug
    result = fetch_company(ats_type, slug, company)
    print(f"{ats_type}/{slug}: {len(result)} Stellen")
    for j in result[:8]:
        print(f"- {j['title']} | {j['location']}")
