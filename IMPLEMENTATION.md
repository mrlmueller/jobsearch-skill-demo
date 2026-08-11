# IMPLEMENTATION — Job-Such-Skill (Stand 2026-07-23, Architektur „lokaler Skill")

*Vom Skill nur bei Bedarf gelesen. Einstieg: `../.claude/skills/jobsuche/SKILL.md`.*

## Architektur-Entscheidung (2026-07-23)

Ein **lokaler Claude-Code-Skill**, 1×/Tag oder 1×/Woche per `/jobsuche` gestartet.
Kein Push-Dienst, kein Standalone-/Homelab-Betrieb, keine zusätzlichen
Dienst-Registrierungen. **Claude** macht das Fuzzy (Portale per Firecrawl-MCP
scrapen, Websuche, Relevanz-Urteil), **Python** das Deterministische (APIs,
Parsen, Dedup, Scoring, SQLite-State, Digest). Einzige Keys: Adzuna
(app_id/app_key lokal in `.env`).

## Pipeline pro Lauf

```
1. Claude: Portale scrapen
   a) markdown-Portale (firecrawl_scrape; stepstone mit proxy:"auto")
        -> data/runs/<datum>_<portal>.md
        -> scrape_portals.py ingest <portal> <datei>
   b) Playwright-Quellen (indeed, germantechjobs, thu, hnu — JS-Apps)
        -> Jobs im Browser extrahieren -> JSON-Datei
        -> scrape_portals.py ingest-json <name> <datei>
2. Python: python scripts/run.py
      arbeitsagentur + arbeitnow + himalayas + jobicy + remoteok + remotive
      + adzuna (.env) + linkedin (Guest-Endpoint)
      + ats (verdeckter Markt: Personio/Greenhouse/… der Seed-Firmen) — je try/except
      -> normalize -> dedup -> score -> upsert -> EIN Digest (inkl. Portal-Jobs)
3. Claude: Websuche-Sweep (firecrawl_search) für Funde außerhalb der Pipeline
4. Claude: Relevanz-Check + kuratierter Bericht (Recall vor Precision:
      Python filtert locker, Claude benennt Rauschen — löscht aber nichts)
```

## Große Börsen — Zugangsweg (verifiziert 2026-07-24, alles OHNE Login)

| Börse | Weg | Anmerkung |
|---|---|---|
| LinkedIn | Guest-API in Python (`fetch_linkedin.py`) | 10 Cards/Seite, kein Volltext; sparsam (Drossel 2 s, 3 Queries) |
| StepStone | Firecrawl `proxy:"auto"` + `parse_stepstone` | 518 Treffer für Werkstudent-SW/Ulm-100km |
| Indeed | Playwright + `ingest-json` | Firecrawl scheitert (document_antibot) |
| Xing | bewusst ausgelassen | Login-Wall; Bestand ≈ StepStone |

## Module

| Skript | Zweck | Besonderheiten |
|---|---|---|
| store.py | SQLite (WAL), jobs/runs/schema_version | Upsert idempotent; „nur Neues" über `notified_at IS NULL` |
| fetch_arbeitsagentur.py | AA-API, 20 Synonym-Queries | Header `X-API-Key: jobboerse-jobsuche`; Volltext-Feld `stellenangebotsBeschreibung`; `homeofficemoeglich` → remote |
| fetch_arbeitnow.py | Offene API, client-gefiltert | 1,5 s Drossel/Seite (sonst 429); ROLE_PATTERN hier definiert |
| fetch_remote.py | Himalayas + Jobicy | Himalayas: KEIN `sort`-Param (400); Filter locationRestrictions leer/DE/EU |
| fetch_adzuna.py | Aggregator (Indeed/Stepstone), Key in .env | nur Snippets; MAX_PAGES=5; überspringt sich ohne Key selbst |
| fetch_linkedin.py | LinkedIn Guest-Endpoint (kein Login) | HTML-Fragment-Parser; Drossel 2 s; kein Volltext |
| scrape_portals.py | `list` / `ingest <portal> <md>` / `ingest-json <name> <json>` | Parser: werkstudenten_jobs, campusjaeger, meinestadt, stepstone, absolventa, get_in_it; Playwright-Quellen via ingest-json |
| normalize.py | → einheitliches Schema | Tech-Tags mit Wortgrenzen (`go` ≠ „Google"); `portal_*`-Dispatch |
| dedup.py | URL-Kanon., sha1(company|title|city), rapidfuzz | Fuzzy nur innerhalb eines Batches |
| score.py | Stufe-0-Regeln aus profile.yaml | keine harten Zusatz-Excludes ohne Rückfrage |
| digest.py | Markdown-Digest, mark_notified | mehrere Läufe/Tag: Anhängen statt Überschreiben |
| rescore.py | Neu-Bewertung nach profile.yaml-Änderung | applied/rejected/interesting bleiben unangetastet |
| enrich.py | Volltext-Nachladen für 20–39er (`list`/`apply`/`mark-dead`) | Kriterium: Beschreibung <600 Zeichen (fängt Adzuna-500er-Snippets); Deckel 15/Lauf; Claude scrapt, Python re-scort. Beleg 2026-07-24: CONTACT 20→80, RENK 25→45, VGL 20→40 |
| envutil.py | Mini-.env-Loader (nur Adzuna) | Umgebungsvariablen gewinnen über Datei |
| seed.py | Verzeichnis-Refresh -> companies_seed.csv | Wiki/WP-REST/Mitgliedsseiten, reines httpx; Websites nie überschreiben; save_rows verweigert Rumpf-Daten |
| ats_detect.py | Karriereseite -> (ats_type, ats_slug) -> CSV | 8 Signaturen; folgt bis 3 Karriere-Links; einmalig, dann dauerhaft billig |
| ats_personio.py | Personio-XML (defusedxml) | 307 = migriert -> Marker für Re-Detektion |
| ats_cleanjson.py | 1 Basis-Adapter, 6 JSON-Profile | greenhouse/lever/ashby/recruitee/smartrecruiters/workday; live verifiziert (GitLab: 186 Stellen) |
| fetch_ats.py | CSV-getriebener Dispatch an die Adapter | Fetch-Logik schreibt NIE selbst auf Platte (Regressionstest) |
| mark.py | Bewerbungsstatus (`<id> applied|rejected|interesting`, `list`) | Feedback-Loop; manuelle Status sind für rescore/upsert unantastbar |

## Am 2026-07-23 live verifiziert

- AA-Header + Detail-Endpoint (base64 refnr) ✓; Volltext bei Extern-Anzeigen oft leer.
- Arbeitnow drosselt (429) bei mehreren Voll-Paginierungen/Tag → 1,5 s Pause eingebaut.
- Himalayas: `sort=dateDesc` abgeschafft (400).
- Adzuna: Keys funktionieren, 50 Treffer/Lauf, viel Personalvermittler-Spam → Score-Filter greift.
- Firecrawl: json-Format 5 Credits, markdown 1 → markdown + Python-Parser.
- Portale (basic-Proxy reicht): campusjaeger, werkstudenten-jobs, jobs.meinestadt.de/ulm/studentenjobs.
  absolventa (neues Schema `/werkstudentenjobs/stadt/ulm`, wenig Ertrag) + germantechjobs (SPA) → Phase 2b in sources.yaml.
- End-to-End-Beleg: „Werkstudent Agentic AI & Multi-Agent-Systeme", Mercedes-Benz
  Tech Innovation Ulm, Score 75 inkl. Seed-Firmen-Bonus, via portal_meinestadt.

## Bekannte Grenzen (ehrlich)

- Scoring ist Stufe 0 (Keywords). Adzuna-/AA-Snippets ohne Volltext können gute
  Jobs unter die Schwelle (40) drücken — deshalb macht Claude den Relevanz-Check
  über die DB, nicht nur über den Digest (`status`-Query zeigt auch 20–39er).
- Upsert aktualisiert Score bestehender Jobs nicht — dafür `rescore.py`.
- meinestadt: nur Seite 1 (neueste zuerst) — bei 1–2 Läufen/Woche ggf. ?page=2 mitscrapen.

## Ausbau bei Bedarf (bewusst NICHT gebaut)

ntfy-Push, systemd/Homelab-Betrieb, E-Mail-Ingestion, ATS-Adapter (Phase 3 im
BUILD-MANIFEST) — nur bei explizitem Bedarf.
