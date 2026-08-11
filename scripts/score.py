"""Stufe-0-Scoring (regelbasiert, gratis) nach profile.yaml."""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

import yaml

from dedup import norm_company
import envutil

ROOT = Path(__file__).parent.parent

TECH_ROLE = re.compile(
    r"softwareentwick|software (developer|engineer)|entwickler|developer|"
    r"programmier|informatik|devops|full[- ]?stack|frontend|backend|"
    r"automatisierung|automation|web ?entwick|it[- ](support|engineer|betrieb)|"
    r"machine learning|data (engineer|scien)|coding|\bki[- ]entwick",
    re.IGNORECASE)
TARGET_ROLE_TITLE = re.compile(r"werkstudent|working student|junior|praktik|intern",
                               re.IGNORECASE)
SIGNALS = {
    "startup_or_small_team": re.compile(r"start[- ]?up|klein\w{0,2} team|small team", re.I),
    "ki_affine_firma": re.compile(r"\bki\b|\bai\b|künstliche intelligenz|llm|gpt|machine learning", re.I),
    "no_cover_letter_or_takehome": re.compile(r"ohne anschreiben|kein anschreiben|take[- ]?home", re.I),
    "flexible_hours_or_remote": re.compile(r"flexib|gleitzeit|remote|home[- ]?office|hybrid", re.I),
    "uebernahme_perspektive": re.compile(r"übernahme|unbefristet nach|festanstellung möglich", re.I),
}
MINUS_SIGNALS = {
    "live_leetcode_signal": re.compile(r"live[- ]?coding|leetcode|coding[- ]challenge", re.I),
    "konzern_massenprozess": re.compile(r"assessment[- ]center|mehrstufiges auswahlverfahren", re.I),
}


@lru_cache(maxsize=1)
def load_profile() -> dict:
    with open(envutil.profile_path(), encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_seed_companies() -> tuple[str, ...]:
    path = ROOT / "data" / "companies_seed.csv"
    if not path.exists():
        return ()
    with open(path, encoding="utf-8-sig", newline="") as f:
        return tuple(norm_company(row["name"]) for row in csv.DictReader(f) if row.get("name"))


def _employment_ok(job: dict, allowed: list[str]) -> bool:
    et = job.get("employment_type")
    if et:
        return et in allowed
    # Kein Typ erkennbar: Titel muss eine Zielrolle sein (Werkstudent/Junior/…).
    # Sonst würden explizite target_titles wie "Junior Software Engineer" am
    # Muss-Filter scheitern, obwohl profile.yaml sie ausdrücklich sucht.
    return bool(TARGET_ROLE_TITLE.search(job.get("title") or ""))


def _location_ok(job: dict, regions: list[str]) -> bool:
    if job.get("remote"):
        return True
    loc = (job.get("location") or "").lower()
    return any(r.lower() in loc for r in regions)


def _role_is_tech(job: dict) -> bool:
    # Titel muss Tech sein ODER >=3 Tech-Tags — 1 Zufallstag ('ki' im Text)
    # reicht nicht, sonst rutschen Nicht-Tech-Rollen durch.
    if TECH_ROLE.search(job.get("title") or ""):
        return True
    return len(job.get("tech_tags") or []) >= 3


def score_job(job: dict, profile: dict | None = None,
              seed_companies: list[str] | None = None) -> dict:
    profile = profile or load_profile()
    seeds = (tuple(norm_company(s) for s in seed_companies)
             if seed_companies is not None else load_seed_companies())
    must = profile["must"]
    plus = profile["plus"]
    minus = profile.get("minus_flags") or {}
    title = job.get("title") or ""
    text = f"{title} {job.get('description') or ''}"
    reasons: list[str] = []

    # ── Muss-Filter (fehlt eins -> ignored, Score bleibt 0) ──
    if any(kw.lower() in title.lower() for kw in profile.get("exclude_keywords") or []):
        job.update(score=0, score_reason="exclude_keyword im Titel", status="ignored")
        return job
    if not _employment_ok(job, must["employment_types"]):
        job.update(score=0, score_reason="Beschäftigungsart passt nicht", status="ignored")
        return job
    if must.get("role_is_tech") and not _role_is_tech(job):
        job.update(score=0, score_reason="keine Tech-Rolle", status="ignored")
        return job
    if must.get("location_in_radius_or_remote") and not _location_ok(
            job, profile["person"]["regions_in_radius"]):
        job.update(score=0, score_reason="außerhalb Radius, nicht remote", status="ignored")
        return job

    # ── Plus-Punkte (additiv) ──
    points = 0
    tags = job.get("tech_tags") or []
    if tags:
        pts = plus["tech_tag_match"] * len(tags)
        points += pts
        reasons.append(f"{len(tags)} Tech-Tags (+{pts})")
    for key, pattern in SIGNALS.items():
        if key == "flexible_hours_or_remote":
            hit = bool(pattern.search(text)) or bool(job.get("remote"))
        else:
            hit = bool(pattern.search(text))
        if hit and key in plus:
            points += plus[key]
            reasons.append(f"{key} (+{plus[key]})")
    if seeds and norm_company(job.get("company") or "") in seeds:
        points += plus["from_companies_seed"]
        reasons.append(f"Seed-Firma (+{plus['from_companies_seed']})")

    # ── Minus-Flags (markieren, nicht ausschließen) ──
    for key, pattern in MINUS_SIGNALS.items():
        if key in minus and pattern.search(text):
            points += minus[key]
            reasons.append(f"{key} ({minus[key]})")

    job.update(score=max(0, min(100, points)),
               score_reason="; ".join(reasons) or "nur Muss-Kriterien erfüllt",
               status="new")
    return job


def score_all(jobs: list[dict], profile: dict | None = None) -> list[dict]:
    return [score_job(j, profile) for j in jobs]
