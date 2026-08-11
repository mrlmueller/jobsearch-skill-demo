"""Dedup: URL-Kanonisierung -> Fingerprint-Hash -> Fuzzy-Match (rapidfuzz)."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

TRACKING_PARAMS = re.compile(r"^(utm_|ref$|source$|fbclid|gclid)", re.IGNORECASE)
LEGAL_FORMS = re.compile(
    r"\b(gmbh( & co\.? kg)?|ag|se|kg|ohg|ug|e\.?\s?v\.?|co\.? kg|inc\.?|ltd\.?)\b",
    re.IGNORECASE)
GENDER_TOKENS = re.compile(
    r"\(\s*[mwfdx]\s*[/|]\s*[mwfdx]\s*([/|]\s*[mwfdx]\s*)?\)|\*in\b|:in\b|/in\b|\(in\)",
    re.IGNORECASE)
PLZ = re.compile(r"\b\d{5}\b")

TITLE_FUZZ_MIN = 88
COMPANY_FUZZ_MIN = 90


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not TRACKING_PARAMS.match(k)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), ""))  # Fragment immer weg


def _fold(text: str) -> str:
    """lowercase + Umlaute -> ae/oe/ue/ss + Akzente weg + Whitespace bündeln."""
    text = text.lower()
    text = (text.replace("ä", "ae").replace("ö", "oe")
                .replace("ü", "ue").replace("ß", "ss"))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def norm_company(company: str) -> str:
    c = LEGAL_FORMS.sub(" ", company or "")
    return _fold(re.sub(r"[^\w\s-]", " ", c))


def norm_title(title: str) -> str:
    t = GENDER_TOKENS.sub(" ", title or "")
    return _fold(re.sub(r"[^\w\s/.+#-]", " ", t))


def norm_city(location: str) -> str:
    return _fold(PLZ.sub(" ", location or ""))


def fingerprint(company: str, title: str, city: str) -> str:
    key = f"{norm_company(company)}|{norm_title(title)}|{norm_city(city)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def fuzzy_is_dup(a: dict, b: dict) -> bool:
    title_score = fuzz.token_sort_ratio(norm_title(a.get("title", "")),
                                        norm_title(b.get("title", "")))
    company_score = fuzz.WRatio(norm_company(a.get("company", "")),
                                norm_company(b.get("company", "")))
    return title_score >= TITLE_FUZZ_MIN and company_score >= COMPANY_FUZZ_MIN


def dedup_all(jobs: list[dict]) -> list[dict]:
    """Setzt canonical_url + dedup_hash; wirft Hash- und Fuzzy-Duplikate raus.

    Fuzzy nur gegen die Kandidaten desselben Laufs (tagesklein laut Manifest).
    """
    kept: list[dict] = []
    seen_hashes: set[str] = set()
    for job in jobs:
        job["canonical_url"] = canonicalize_url(job.get("url") or "")
        job["dedup_hash"] = fingerprint(job.get("company", ""),
                                        job.get("title", ""),
                                        job.get("location", ""))
        if job["dedup_hash"] in seen_hashes:
            continue
        if any(fuzzy_is_dup(job, k) for k in kept):
            continue
        seen_hashes.add(job["dedup_hash"])
        kept.append(job)
    return kept
