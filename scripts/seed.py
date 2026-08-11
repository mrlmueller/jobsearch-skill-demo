"""Seed-Refresh: regionale Verzeichnisse -> data/companies_seed.csv anreichern.

Quellen (alle offen, reines httpx — kein Firecrawl nötig):
  - Science-Park-Wiki (MediaWiki-API, Batch-Inhalte, Homepage= im Template)
  - Innovationsregion Ulm (WordPress-REST, externe Links im Profiltext)
  - Startup-Region Ulm (Mitgliedsseiten, erster externer Link)

Regeln: vorhandene Websites werden NIE überschrieben; unbekannte Firmen
werden ergänzt. Aufruf: python scripts/seed.py
"""
from __future__ import annotations

import csv
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import httpx

from dedup import norm_company

ROOT = Path(__file__).parent.parent
CSV_PATH = ROOT / "data" / "companies_seed.csv"

WIKI_API = "https://wissenschaftsstadt.uni-ulm.de/mediawiki/api.php"
IRU_API = "https://innovationsregion-ulm.de/wp-json/wp/v2/unternehmen"
SRU_LIST = "https://startup-region-ulm.de/startups/"

UA = {"User-Agent": "Mozilla/5.0 (jobsearch-skill; personal use)"}
THROTTLE = 1.0

# Footer-/Rechtliches-Rauschen auf Mitglieds-/Profilseiten
NOISE_DOMAINS = ("ihk.de", "subreality.de", "openstreetmap.org", "wp.me",
                 "instagram.", "linkedin.", "facebook.", "youtube.",
                 "google.", "gstatic.", "wordpress.", "twitter.", "x.com",
                 "mailto:", "startup-region-ulm.de", "innovationsregion-ulm.de",
                 "uni-ulm.de")

URL_RE = re.compile(r"https?://[^\s\]\|<}\"')]+")
HOMEPAGE_RE = re.compile(r"Homepage\s*=\s*(https?://\S+)")
HREF_RE = re.compile(r'href="(https?://[^"]+)"')


def slugify(name: str) -> str:
    text = name.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-")


def _is_noise(url: str) -> bool:
    return any(d in url.lower() for d in NOISE_DOMAINS)


def wiki_website(content: str) -> str | None:
    m = HOMEPAGE_RE.search(content)
    if m:
        return m.group(1).rstrip("|}").strip()
    for url in URL_RE.findall(content):
        if not _is_noise(url):
            return url
    return None


def member_website(html: str) -> str | None:
    for url in HREF_RE.findall(html):
        if not _is_noise(url):
            return url
    return None


def member_name(html: str) -> str | None:
    """Firmenname steht im <h1>; der <title> ist nur 'Startup-Region Ulm'."""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if not m:
        return None
    import html as html_lib
    return html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() or None


def merge_updates(rows: list[dict], updates: list[dict], source: str) -> dict:
    """Websites in bestehende Zeilen füllen (nie überschreiben), Neue anlegen."""
    by_norm = {norm_company(r["name"]): r for r in rows}
    filled = added = 0
    today = date.today().isoformat()
    for u in updates:
        name, website = u.get("name"), u.get("website")
        if not name:
            continue
        row = by_norm.get(norm_company(name))
        if row is not None:
            if website and not (row.get("website") or "").strip():
                row["website"] = website
                row["last_verified"] = today
                filled += 1
        else:
            new_row = {k: "" for k in rows[0].keys()} if rows else {}
            new_row.update(company_id=slugify(name), name=name,
                           location_city="Ulm", location_region="Ulm",
                           commute_minutes="0", website=website or "",
                           tech_relevance="1", source=source,
                           source_url=u.get("source_url", ""),
                           last_verified=today, scrape_status="ok")
            rows.append(new_row)
            by_norm[norm_company(name)] = new_row
            added += 1
    return {"filled": filled, "added": added}


# ── Live-Fetcher ─────────────────────────────────────────────────────────

def fetch_wiki(category: str) -> list[dict]:
    updates, cont = [], {}
    while True:
        params = {"action": "query", "generator": "categorymembers",
                  "gcmtitle": category, "gcmlimit": 50,
                  "prop": "revisions", "rvprop": "content", "rvslots": "main",
                  "format": "json", **cont}
        r = httpx.get(WIKI_API, params=params, headers=UA, timeout=30,
                      follow_redirects=True)
        r.raise_for_status()
        d = r.json()
        for p in (d.get("query", {}).get("pages", {}) or {}).values():
            try:
                content = p["revisions"][0]["slots"]["main"]["*"]
            except (KeyError, IndexError):
                continue
            updates.append({"name": p["title"], "website": wiki_website(content),
                            "source_url": f"{WIKI_API}?curid={p.get('pageid')}"})
        cont = d.get("continue") or {}
        if not cont:
            return updates
        time.sleep(THROTTLE)


def fetch_innovationsregion() -> list[dict]:
    import html as html_lib
    updates, page = [], 1
    while True:
        r = httpx.get(IRU_API, params={"per_page": 100, "page": page},
                      headers=UA, timeout=30, follow_redirects=True)
        if r.status_code == 400:  # hinter letzter Seite
            return updates
        r.raise_for_status()
        entries = r.json()
        if not entries:
            return updates
        for e in entries:
            hrefs = HREF_RE.findall(e["content"]["rendered"])
            website = next((h for h in hrefs if not _is_noise(h)), None)
            updates.append({"name": html_lib.unescape(e["title"]["rendered"]),
                            "website": website, "source_url": e.get("link", "")})
        page += 1
        time.sleep(THROTTLE)


def fetch_startup_region() -> list[dict]:
    r = httpx.get(SRU_LIST, headers=UA, timeout=30, follow_redirects=True)
    r.raise_for_status()
    member_urls = sorted(set(re.findall(
        r'https://startup-region-ulm\.de/mitglied/[^"\s]+/', r.text)))
    updates = []
    for url in member_urls:
        try:
            time.sleep(THROTTLE)
            page = httpx.get(url, headers=UA, timeout=20, follow_redirects=True)
            page.raise_for_status()
            name = member_name(page.text)
            if not name:
                continue
            updates.append({"name": name, "website": member_website(page.text),
                            "source_url": url})
        except Exception as e:
            print(f"[seed] {url} fehlgeschlagen: {e}", file=sys.stderr)
    return updates


def load_rows() -> list[dict]:
    if not CSV_PATH.exists():  # frischer Klon ohne eigene Seed-Liste
        return []
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


EXPECTED_COLUMNS = {"company_id", "name", "website", "ats_type", "ats_slug",
                    "ats_feed_url", "source"}


def save_rows(rows: list[dict]) -> None:
    """Schutz gegen versehentliches Überschreiben mit Rumpf-Daten
    (Lehre vom 2026-07-24: ein Test hat die CSV mit Fake-Zeilen ersetzt)."""
    if not rows or not EXPECTED_COLUMNS.issubset(rows[0].keys()) or len(rows) < 50:
        raise ValueError(
            f"save_rows verweigert: {len(rows)} Zeilen, Spalten passen nicht — "
            "sieht nicht nach der echten companies_seed.csv aus")
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rows = load_rows()
    total = {"filled": 0, "added": 0}
    for label, fetch_fn in [
        ("science-park-wiki (Firmen)", lambda: fetch_wiki("Kategorie:Firmen")),
        ("science-park-wiki (Start-Ups)", lambda: fetch_wiki("Kategorie:Start-Ups")),
        ("innovationsregion", fetch_innovationsregion),
        ("startup-region", fetch_startup_region),
    ]:
        try:
            updates = fetch_fn()
            stats = merge_updates(rows, updates, source=label.split(" ")[0])
            print(f"[{label}] {len(updates)} Einträge -> {stats['filled']} Websites "
                  f"ergänzt, {stats['added']} Firmen neu")
            for k in total:
                total[k] += stats[k]
        except Exception as e:
            print(f"[{label}] FEHLGESCHLAGEN: {e}", file=sys.stderr)
    save_rows(rows)
    with_web = sum(1 for r in rows if (r.get("website") or "").strip())
    print(f"\nGesamt: {total['filled']} Websites ergänzt, {total['added']} Firmen neu. "
          f"{with_web}/{len(rows)} Firmen haben jetzt eine Website.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
