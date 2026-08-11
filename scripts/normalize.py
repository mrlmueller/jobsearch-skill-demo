"""Roh-Jobs beider Quellen → einheitliches Job-Schema (Manifest 'Zielformat')."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import yaml
import envutil

ROOT = Path(__file__).parent.parent


@lru_cache(maxsize=1)
def default_anchors() -> tuple[str, ...]:
    with open(envutil.profile_path(), encoding="utf-8") as f:
        return tuple(yaml.safe_load(f).get("tech_anchors") or [])

EMPLOYMENT_TYPES = [
    ("werkstudent", r"werkstudent|working student"),
    ("praktikum", r"praktik|intern(ship)?\b"),
    ("teilzeit", r"teilzeit|part[- ]?time"),
    ("vollzeit", r"vollzeit|full[- ]?time"),
]

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text)).strip()


def extract_tech_tags(text: str, anchors: list[str]) -> list[str]:
    """Anker mit Wortgrenzen matchen — 'go' darf nicht in 'Google' treffen."""
    found = []
    for anchor in anchors:
        pattern = r"(?<![a-z0-9])" + re.escape(anchor.lower()) + r"(?![a-z0-9])"
        if re.search(pattern, text.lower()):
            found.append(anchor)
    return found


def detect_employment_type(text: str) -> str | None:
    for name, pattern in EMPLOYMENT_TYPES:
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return None


def _iso_date(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    return str(value)[:10]


def _base_job(raw: dict) -> dict:
    return {
        "dedup_hash": None,        # setzt dedup.py
        "canonical_url": None,     # setzt dedup.py
        "source": raw.get("_source"),
        "source_job_id": None,
        "title": None,
        "company": None,
        "location": None,
        "remote": False,
        "url": None,
        "description": "",
        "salary": None,
        "posted_at": None,
        "tech_tags": [],
        "employment_type": None,
        "score": 0,
        "score_reason": None,
        "status": "new",
        "raw_json": json.dumps(
            {k: v for k, v in raw.items() if not k.startswith("_")},
            ensure_ascii=False),
    }


def _normalize_arbeitsagentur(raw: dict) -> dict:
    job = _base_job(raw)
    ort = raw.get("arbeitsort") or {}
    job.update(
        source_job_id=raw.get("refnr"),
        title=raw.get("titel") or raw.get("beruf"),
        company=raw.get("arbeitgeber"),
        location=ort.get("ort"),
        remote=bool(raw.get("_homeoffice")),
        url=raw.get("_url"),
        description=raw.get("_description", ""),
        posted_at=_iso_date(raw.get("aktuelleVeroeffentlichungsdatum")),
    )
    return job


def _normalize_arbeitnow(raw: dict) -> dict:
    job = _base_job(raw)
    job.update(
        source_job_id=raw.get("slug"),
        title=raw.get("title"),
        company=raw.get("company_name"),
        location=raw.get("location"),
        remote=bool(raw.get("remote")),
        url=raw.get("url"),
        description=strip_html(raw.get("description") or ""),
        posted_at=_iso_date(raw.get("created_at")),
    )
    return job


def _normalize_himalayas(raw: dict) -> dict:
    job = _base_job(raw)
    restrictions = raw.get("locationRestrictions") or []
    job.update(
        source_job_id=raw.get("guid"),
        title=raw.get("title"),
        company=raw.get("companyName"),
        location="Remote (" + ", ".join(restrictions) + ")" if restrictions else "Remote",
        remote=True,
        url=raw.get("applicationLink"),
        description=strip_html(raw.get("description") or raw.get("excerpt") or ""),
        salary=(f"{raw['minSalary']}–{raw['maxSalary']} {raw.get('currency') or ''}".strip()
                if raw.get("minSalary") else None),
        posted_at=_iso_date(raw.get("pubDate")),
    )
    return job


def _normalize_jobicy(raw: dict) -> dict:
    job = _base_job(raw)
    job.update(
        source_job_id=str(raw.get("id")),
        title=raw.get("jobTitle"),
        company=raw.get("companyName"),
        location=f"Remote ({raw.get('jobGeo')})" if raw.get("jobGeo") else "Remote",
        remote=True,
        url=raw.get("url"),
        description=strip_html(raw.get("jobDescription") or raw.get("jobExcerpt") or ""),
        salary=raw.get("annualSalaryMin") and
               f"{raw.get('annualSalaryMin')}–{raw.get('annualSalaryMax')} {raw.get('salaryCurrency') or ''}".strip(),
        posted_at=_iso_date(raw.get("pubDate")),
    )
    return job


def _normalize_adzuna(raw: dict) -> dict:
    job = _base_job(raw)
    salary = None
    if raw.get("salary_min"):
        salary = f"{int(raw['salary_min'])}–{int(raw.get('salary_max') or raw['salary_min'])} EUR/Jahr"
    job.update(
        source_job_id=str(raw.get("id")),
        title=raw.get("title"),
        company=(raw.get("company") or {}).get("display_name"),
        location=(raw.get("location") or {}).get("display_name"),
        remote=False,  # Adzuna hat kein Remote-Flag; Radius-Filter greift
        url=raw.get("redirect_url"),
        description=strip_html(raw.get("description") or ""),
        salary=salary,
        posted_at=_iso_date(raw.get("created")),
    )
    return job


def _normalize_portal(raw: dict) -> dict:
    job = _base_job(raw)
    posted = raw.get("posted_date")
    if posted and re.match(r"\d{2}\.\d{2}\.\d{4}$", posted):
        d, m, y = posted.split(".")
        posted = f"{y}-{m}-{d}"
    job.update(
        source_job_id=raw.get("url"),
        title=raw.get("title"),
        company=raw.get("company"),
        location=raw.get("location"),
        remote=bool(raw.get("homeoffice")),
        url=raw.get("url"),
        description=raw.get("snippet") or "",
        salary=raw.get("salary"),
        posted_at=posted,
    )
    return job


def _normalize_linkedin(raw: dict) -> dict:
    job = _base_job(raw)
    job.update(
        source_job_id=raw.get("job_id"),
        title=raw.get("title"),
        company=raw.get("company"),
        location=raw.get("location"),
        remote="remote" in (raw.get("location") or "").lower(),
        url=raw.get("url"),
        description="",  # Guest-Endpoint liefert keinen Volltext
        posted_at=raw.get("posted_at"),
    )
    return job


def _normalize_remoteok(raw: dict) -> dict:
    job = _base_job(raw)
    salary = None
    if raw.get("salary_min"):
        salary = f"{raw['salary_min']}–{raw.get('salary_max') or raw['salary_min']} USD/Jahr"
    job.update(
        source_job_id=str(raw.get("id")),
        title=raw.get("position"),
        company=raw.get("company"),
        location=f"Remote ({raw.get('location')})" if raw.get("location") else "Remote",
        remote=True,
        url=raw.get("url"),
        description=strip_html(raw.get("description") or ""),
        salary=salary,
        posted_at=_iso_date(raw.get("date")),
    )
    return job


def _normalize_remotive(raw: dict) -> dict:
    job = _base_job(raw)
    loc = raw.get("candidate_required_location")
    job.update(
        source_job_id=str(raw.get("id")),
        title=raw.get("title"),
        company=raw.get("company_name"),
        location=f"Remote ({loc})" if loc else "Remote",
        remote=True,
        url=raw.get("url"),
        description=strip_html(raw.get("description") or ""),
        salary=raw.get("salary") or None,
        posted_at=_iso_date(raw.get("publication_date")),
    )
    return job


_NORMALIZERS = {
    "arbeitsagentur": _normalize_arbeitsagentur,
    "adzuna": _normalize_adzuna,
    "linkedin": _normalize_linkedin,
    "remoteok": _normalize_remoteok,
    "remotive": _normalize_remotive,
    "arbeitnow": _normalize_arbeitnow,
    "himalayas": _normalize_himalayas,
    "jobicy": _normalize_jobicy,
}


def _normalize_ats(raw: dict) -> dict:
    """ATS-Adapter (ats_personio, ats_greenhouse, …) liefern schon saubere Felder."""
    job = _base_job(raw)
    location = raw.get("location") or ""
    job.update(
        source_job_id=str(raw.get("job_id")),
        title=raw.get("title"),
        company=raw.get("company"),
        location=location,
        remote="remote" in location.lower(),
        url=raw.get("url"),
        description=raw.get("description") or "",
        salary=raw.get("salary"),
        posted_at=raw.get("posted_at"),
    )
    return job


def normalize_job(raw: dict, anchors: list[str] | None = None) -> dict:
    source = raw.get("_source") or ""
    if source.startswith("portal_"):
        normalizer = _normalize_portal
    elif source.startswith("ats_"):
        normalizer = _normalize_ats
    elif source in _NORMALIZERS:
        normalizer = _NORMALIZERS[source]
    else:
        raise ValueError(f"Unbekannte Quelle: {source!r}")
    job = normalizer(raw)
    text = f"{job['title'] or ''} {job['description'] or ''} " + " ".join(
        (raw.get("tags") or []) + (raw.get("job_types") or [])) + " " + " ".join(
        str(raw.get(k) or "") for k in ("employment_hint", "schedule",
                                        "seniority", "keywords"))
    job["tech_tags"] = extract_tech_tags(text, list(anchors or default_anchors()))
    job["employment_type"] = detect_employment_type(text)
    return job


def normalize_all(raws: list[dict], anchors: list[str] | None = None) -> list[dict]:
    return [normalize_job(r, anchors) for r in raws]
