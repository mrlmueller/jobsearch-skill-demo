# BUILD-MANIFEST — Was jedes Skript tun muss (Bau-Checkliste)
*Abarbeiten in dieser Reihenfolge. Nach jedem Skript einen echten Testlauf zeigen. Details/Belege in ../BUILD-START-HERE.md + Referenzdateien.*

## Gemeinsame Konventionen
- Python 3.11+. Pfade relativ: `ROOT = Path(__file__).parent.parent`; DB `ROOT/data/seen.sqlite`; Config `ROOT/config/*.yaml`; Digest `ROOT/digests/`.
- Config laden: `yaml.safe_load` (pip: pyyaml). HTTP: `httpx` oder `requests` + Timeout überall + `tenacity`-Backoff bei 429/5xx.
- Jede Fetch-Funktion gibt eine Liste ROH-Dicts zurück; `normalize.py` macht das einheitliche Schema. Keine Quelle darf den Lauf abbrechen (try/except in run.py).

## Einheitliches Job-Schema (Zielformat nach normalize)
`{dedup_hash, canonical_url, source, source_job_id, title, company, location, remote(bool), url, description, salary, posted_at, tech_tags[], employment_type, score, score_reason, status, first_seen, last_seen, seen_count, notified_at, raw_json}`

---
## PHASE 1 (KEINE Keys) — Reihenfolge:

### [x] 1. store.py
- `init_db()`: WAL, Tabellen `jobs`/`runs`/`schema_version` (Schema siehe BUILD-START-HERE §4.1). Indizes.
- `upsert(job)`: `INSERT … ON CONFLICT(dedup_hash) DO UPDATE SET last_seen=now, seen_count=seen_count+1`. Gibt zurück, ob NEU.
- `new_for_digest(min_score, limit)`: `WHERE notified_at IS NULL AND status='new' AND score>=? ORDER BY score DESC LIMIT ?`.
- `mark_notified(ids)`, `start_run()/finish_run(...)`.
- TEST: DB anlegen, Dummy-Job upserten, zweites Upsert erhöht seen_count statt Duplikat.

### [x] 2. fetch_arbeitsagentur.py
- Für jedes `target_titles_de/en` aus profile.yaml eine Query (Params/Header siehe sources.yaml). Paginieren bis leer/size.
- Roh-Jobs sammeln; optional Volltext via detail_endpoint (base64 refnr) für Top-Treffer.
- TEST: echter Live-Call, >0 Treffer für "Werkstudent Softwareentwicklung" wo=Ulm umkreis=100. Header-Wert bestätigen.

### [x] 3. fetch_arbeitnow.py
- Alle Seiten paginieren. Client-seitig filtern (title/tags/job_types ~ Zielrollen; location im Radius ODER remote==true).
- TEST: Live-Call, gefilterte Treffer plausibel.

### [x] 4. normalize.py
- Beide Quellen → Zielschema. Tech-Tags aus title+description gegen `tech_anchors`. remote-Flag bestimmen. posted_at ISO.
- TEST: gemischte Rohliste rein → sauberes Schema raus.

### [x] 5. dedup.py  (pip: rapidfuzz)
- `canonicalize_url()`, `fingerprint()` → `dedup_hash = sha1(company|title|city)`, `fuzzy_is_dup()` (token_sort_ratio title>=88 UND WRatio company>=90, nur gegen tageskleine Kandidaten).
- TEST: dieselbe Stelle aus 2 Quellen wird als 1 erkannt; zwei verschiedene bleiben getrennt.

### [x] 6. score.py
- Stufe-0-Regeln aus profile.yaml: Muss-Filter (sonst 'ignored'), exclude_keywords im Titel raus, Plus-Punkte additiv, Minus-Flags. `score` 0–100 + `score_reason`.
- TEST: eine klar passende und eine klar unpassende Stelle → erwartete Scores.

### [x] 7. digest.py + run.py
- run.py: start_run → je Quelle try/except (fetch→normalize) → alles dedup → score → store.upsert; finish_run mit Zählern.
- digest.py: `new_for_digest()` → `digests/YYYY-MM-DD_digest.md` (Kopf + Treffer nach Score + Fußnote fehlgeschlagene Quellen) → `mark_notified()`.
- TEST: **Kompletter Lauf erzeugt echten Digest mit echten Stellen. Zweiter Lauf zeigt nur NEUES.**  ← ENDE PHASE 1

---
## PHASE 2 (kostenlose Keys, .env) — dann:
- [x] fetch_adzuna.py, fetch_remote.py (himalayas/jobicy) — sources.yaml.
- [x] scrape_portals.py (3 Portale verifiziert; absolventa/germantechjobs -> Phase 2b, s. sources.yaml) (Firecrawl: actions für „mehr laden", json-Schema-Extraktion; Portale in sources.yaml). Rezepte in ../..19 §4.
- [~] notify.py (ntfy-Push): war gebaut, wurde wieder entfernt — das Werkzeug läuft bewusst ohne Push-Betrieb (siehe Architektur-Entscheidung in IMPLEMENTATION.md).
- [x] SKILL.md geschrieben (.claude/skills/jobsuche/, Frontmatter gegen Doku Juli 2026 verifiziert) (Frontmatter name/description/allowed-tools; Body ruft run.py; Push-Alert-Checkliste). Frontmatter gegen aktuelle Doku prüfen.

## PHASE 3 (verdeckter Markt) — dann:
- [x] ats_personio.py (defusedxml, 307 abfangen), ats_cleanjson.py (6 Profile, live: GitLab 186 Stellen), ats_detect.py (8 Signaturen; Lauf 2026-07-24: 7 ATS bei 144 Firmen erkannt) + fetch_ats.py in run.py.
- [x] seed.py (Wiki/WP-REST/Mitgliedsseiten, reines httpx; 2026-07-24: 144/279 Firmen mit Website, 101 neu).
- [~] Karriereseiten-Monitore: BEWUSST AUSGELASSEN (bewusst keine stehende Infrastruktur; 2x/Woche-Läufe decken das ab).
- [~] Scoring Stufe 1+2: BEWUSST AUSGELASSEN — Claude ist der Urteils-Layer bei jedem Lauf (Grenzfall-Review + enrich.py ersetzen Embedding/LLM-Blend).

## PHASE 4 (Betrieb) — dann:
- [ ] Proxmox LXC + systemd-Timer + OnFailure→ntfy + Totmann-Alert. ../..19 §6.
- [ ] E-Mail-Alert-Ingestion (Gmail-API read-only → beautifulsoup → Pipeline, source='*_mail'). ../..19 §8.

---
## Definition of Done (Phase 1)
Ein `python scripts/run.py` erzeugt eine datierte Digest-Datei mit echten, relevanten Werkstudenten-/Junior-Stellen aus Arbeitsagentur + Arbeitnow, dedupliziert und nach Score sortiert; ein zweiter Lauf listet nur neue Treffer. Kein Key, keine Fixkosten.
