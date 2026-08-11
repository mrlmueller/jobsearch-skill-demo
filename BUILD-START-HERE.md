# BUILD — START HIER (Kickoff für eine neue Claude-Code-Session)
*Erstellt: 2026-07-23. Zweck: In einer FRISCHEN Claude-Code-Session sofort mit dem strukturierten Bau des Job-Such-Skills beginnen — ohne Vorwissen aus der bisherigen Konversation.*

---

## 0. So startest du (wörtlich)
1. Neue Claude-Code-Session im Elternordner dieses Verzeichnisses öffnen.
2. Diesen Prompt einfügen:

> **„Wir bauen einen lokalen Job-Such-Skill. Lies zuerst `jobsearch-skill/BUILD-START-HERE.md` komplett, dann `jobsearch-skill/config/profile.yaml`, `jobsearch-skill/config/sources.yaml` und `jobsearch-skill/scripts/BUILD-MANIFEST.md`. Danach bauen wir Phase 1 (MVP) exakt nach dem Manifest — Arbeitsagentur + Arbeitnow → erster echter Digest, ohne API-Keys. Arbeite testgetrieben und zeig mir nach jedem Skript ein echtes Ergebnis. Frag nur nach, wenn eine Entscheidung wirklich meine ist."**

3. Für tiefe technische Details verweist dich dieses Dokument punktuell auf `../2026-07-23_16_Case-Study-1_Vertiefung.md` (Quellen/APIs) und `../2026-07-23_19_Case-Study-2_Vertiefung_Bauspezifikation.md` (Architektur). Alles Nötige für Phase 1 steht aber schon hier.

---

## 1. Worum es geht (Kurzkontext — mehr braucht die Bau-Session nicht)
**Nutzer:** Full-Stack-Entwickler (Python, TypeScript/React/Next.js, Go, Docker, LLM/KI-gestützt), Raum Ulm, kurz vor B.Sc.-Abschluss. Homelab mit Proxmox.
**Ziel des Skills:** Wiederholt laufendes System, das automatisiert Werkstudenten-/Junior-Stellen im Bereich **Softwareentwicklung / Automatisierung / Internal Tools / Full-Stack** findet — Raum Ulm (1 h Bahn) **oder** Remote — dedupliziert, bewertet und als Digest ausgibt. Läuft, bis ein Job gefunden ist.
**Warum als Skill:** Suche als System statt Fleißarbeit; nutzt die Stärke des Nutzers (Bauen). Gewollt sind Tiefe und Vollständigkeit, bewusste Mehrfach-Abdeckung, damit nichts entgeht.
**Prinzip:** Deterministik in Python (API-Pulls, Normalize, Dedup, Scoring, SQLite-State), Fuzzy in Claude+Firecrawl (Portale scrapen, Relevanz beurteilen, Digest). Zustand ist Pflicht — ab Lauf 2 nur noch NEUES im Digest.

## 2. Arbeitsweise (wichtig)
- **Iterativ, kontrolliert.** Nach jedem Bau-Schritt ein echtes Ergebnis zeigen, dann prüfen, ob weiter. Nicht 10 Dinge gleichzeitig aufreißen.
- **Testgetrieben / verifiziert.** Nichts als „fertig" behaupten ohne echten Lauf mit echtem Output.
- **Ehrlichkeit.** Wenn eine Quelle nicht geht oder ein Wert unsicher ist, sagen — nicht kaschieren.
- **Tempo bestimmt der Nutzer.** Reversible Bau-Schritte einfach machen; nur bei echten Entscheidungen fragen.
- **Parallele Recherche-Agenten** erlaubt, aber max. 10 gleichzeitig, dann nächste Welle (falls nochmal recherchiert wird — für den Bau meist nicht nötig).

## 3. Zielstruktur des Skills
```
jobsearch-skill/
├── BUILD-START-HERE.md        ← dieses Dokument
├── SKILL.md                   ← (Phase 2) Claude-Code-Skill-Definition
├── IMPLEMENTATION.md          ← (Phase 3) ausgelagerte Details
├── config/
│   ├── profile.yaml           ← FERTIG: Suchprofil, Keywords, Radius, Scoring-Kriterien
│   └── sources.yaml           ← FERTIG: alle verifizierten Quellen mit Endpoints
├── scripts/
│   ├── BUILD-MANIFEST.md      ← FERTIG: was jedes Skript tun muss (Bau-Checkliste)
│   ├── run.py                 ← (bauen) Orchestrator
│   ├── fetch_arbeitsagentur.py← (Phase 1) API, KEIN Key
│   ├── fetch_arbeitnow.py     ← (Phase 1) API, KEIN Key
│   ├── normalize.py           ← (Phase 1) → einheitliches Job-Schema
│   ├── dedup.py               ← (Phase 1) URL → sha1-Hash → rapidfuzz
│   ├── score.py               ← (Phase 1) Stufe-0-Regeln
│   ├── store.py               ← (Phase 1) SQLite seen.db
│   ├── digest.py              ← (Phase 1) datierte Markdown-Ausgabe
│   ├── fetch_adzuna.py / fetch_remote.py     ← (Phase 2)
│   ├── scrape_portals.py                     ← (Phase 2, Firecrawl)
│   ├── ats_personio.py / ats_cleanjson.py    ← (Phase 3)
│   ├── ats_detect.py                          ← (Phase 3)
│   └── notify.py                              ← (Phase 2/4, ntfy)
├── data/
│   ├── seen.sqlite            ← Zustand (wird erzeugt)
│   ├── companies_seed.csv     ← FERTIG: 171 Firmen Raum Ulm
│   └── runs/                  ← Roh-Dumps je Lauf
└── digests/
    └── YYYY-MM-DD_digest.md   ← Ergebnis je Lauf
```

## 4. PHASE 1 — MVP (heute baubar, KEINE API-Keys nötig)
Ziel: Erster echter Digest aus zwei offenen, kostenlosen APIs. Reihenfolge:

### 4.1 `store.py` + SQLite-Schema
WAL-Mode. Tabelle `jobs` (Kern): `dedup_hash TEXT UNIQUE`, `canonical_url`, `source`, `source_job_id`, `title`, `company`, `location`, `url`, `description`, `salary`, `posted_at`, `first_seen`, `last_seen`, `seen_count`, `score`, `score_reason`, `status DEFAULT 'new'` (new|interesting|applied|rejected|ignored), `notified_at`, `raw_json`. Indizes auf dedup_hash(UNIQUE), canonical_url, status, notified_at, first_seen. Plus `runs`-Tabelle (started/finished, sources_ok/failed, jobs_new/seen, status, note) + `schema_version`.
**Upsert idempotent:** `INSERT … ON CONFLICT(dedup_hash) DO UPDATE SET last_seen=now, seen_count=seen_count+1`.
**„Nur Neues":** `WHERE notified_at IS NULL AND status='new' AND score>=:min ORDER BY score DESC LIMIT :n`; nach Versand `notified_at=now`.

### 4.2 `fetch_arbeitsagentur.py` (KEIN Key)
```
GET https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/app/jobs
    ?was=<synonym>&wo=Ulm&umkreis=100&arbeitszeit=tz;ho&veroeffentlichtseit=14&size=100&page=1
Header: X-API-Key: jobboerse-jobsuche
```
Pro Titel-Synonym (aus profile.yaml, KEIN Boolean!) eine Query. Treffer → `refnr` merken. Volltext optional:
`GET .../pc/v4/jobdetails/{base64(refnr)}` (gleicher Header). Rückgabe: Liste Roh-Jobs.
Am Live-Call bestätigen, dass der Header-Wert noch stimmt (sonst Fallback `X-API-KEY: jobboerse-jobsuche`).

### 4.3 `fetch_arbeitnow.py` (KEIN Key)
```
GET https://www.arbeitnow.com/api/job-board-api?page=1   (dann page++ bis leer/meta)
```
Kein Header. Response `data[]` mit `title, company_name, location, remote, url, description(HTML), tags, job_types, created_at`. **Client-seitig filtern:** title/tags ~ (Werkstudent|Junior|Software|Developer|Automation), location ~ Ulm-Radius ODER remote==true.

### 4.4 `normalize.py`
Beide Quellen → einheitliches Schema (siehe 4.1-Felder). Tech-Tags aus Text extrahieren (profile.yaml `tech_anchors`). `posted_at` als ISO-String.

### 4.5 `dedup.py`
1. **URL-Kanonisierung:** utm_*/ref/Fragmente strippen → `canonical_url`.
2. **Fingerprint:** company (lowercase, Rechtsformen gmbh/ag/se/kg raus), title ((m/w/d)/Gender raus), city (PLZ raus, Umlaute normalisieren via unicodedata) → `dedup_hash = sha1(company|title|city)`.
3. **Fuzzy nur gegen tageskleine Kandidaten:** `rapidfuzz` (`token_sort_ratio(title)>=88` UND `WRatio(company)>=90`). `pip install rapidfuzz`.

### 4.6 `score.py` (Stufe 0 Regeln, gratis)
Muss (sonst `status='ignored'`): Beschäftigungsart passend, Tätigkeit = Entwicklung/Automatisierung/IT, Ort im Radius ODER remote. Minus-Keywords raus. Plus: Tech-Tag-Treffer additiv 0–100 (Gewichte aus profile.yaml). Ergebnis in `score` + kurze `score_reason`.

### 4.7 `digest.py` + `run.py`
`run.py` orchestriert: für jede Quelle try/except (eine kaputte Quelle bricht nicht alles ab, `runs`-Zeile schreiben) → normalize → dedup → score → store (upsert). Dann `digest.py`: „nur Neues"-Query → datierte Markdown-Datei `digests/YYYY-MM-DD_digest.md`: Kopf (Datum, #Quellen ok/fehl, #neu, #gesamt), neue Treffer nach Score sortiert (Titel · Firma · Ort/Remote · Score · 1 Satz warum · Direktlink · Bewerbungsmodus falls erkennbar), Fußnote fehlgeschlagene Quellen. Nach Ausgabe `notified_at=now`.

**➜ ENDE PHASE 1: Ein echter Digest aus Arbeitsagentur + Arbeitnow. Ab hier liefert der Skill Wert.**

## 5. PHASE 2 — Breite (mit kostenlosen Keys)
`fetch_adzuna.py` (app_id/app_key gratis), `fetch_remote.py` (Himalayas/Jobicy offen), `scrape_portals.py` via Firecrawl (Workwise, werkstudenten-jobs.de, meinestadt.de, Absolventa, GermanTechJobs — Details/Scrapebarkeit in `../..16`), `notify.py` (ntfy-Push). Keys in `.env` (NICHT ins Repo). SKILL.md schreiben (orchestriert + Push-Alert-Checkliste).

## 6. PHASE 3 — Verdeckter Markt (der wertvollste Teil)
`ats_personio.py` (`<slug>.jobs.personio.de/xml`, 307=migriert abfangen), `ats_cleanjson.py` (Greenhouse/Lever/Ashby/Recruitee/SmartRecruiters/Workday — ein Basis-Adapter, mehrere Configs; exakte Endpoints in `../..19` §3), `ats_detect.py` (Karriereseite→ATS+Slug→in companies_seed.csv schreiben), Karriereseiten-Monitore (Firecrawl-Monitor). Scoring-Stufe 1+2: lokales Embedding (sentence-transformers, multilingual-MiniLM) + LLM nur Top-5–15 (gpt-4o-mini/Groq), Blend `final=0.4*emb+0.6*llm`, hartes LLM-Tageslimit.

## 7. PHASE 4 — Dauerbetrieb (Homelab)
Proxmox Debian-LXC + systemd-Timer (`OnCalendar=*-*-* 07,18:00:00`, `Persistent=true`), `OnFailure=`→ntfy, „Totmann"-Alert bei >36 h ohne Erfolg. E-Mail-Alert-Ingestion (Gmail-API read-only → beautifulsoup → in Pipeline) für Indeed/StepStone/LinkedIn. Details in `../..19` §6/§8.

## 8. Kosten
Phase 1: 0 €. Firecrawl (ab Phase 2): Free 1.000 / Hobby 5.000 Credits — reicht realistisch (basic-Proxy default, enhanced nur für blockende Seiten; map→batch statt Blind-Crawl). LLM-Scoring: Cent-Bereich. Keine laufenden Fixkosten zwingend.

## 9. Am Bautag zu verifizieren (kurz)
- Arbeitsagentur-Header-Wert am Live-Call bestätigen.
- Firecrawl json-Format-Credit-Aufschlag am Dashboard messen; MCP erwartet `stealth` oder `enhanced`.
- Adzuna Free-Tier-Tageslimit + ToS Privatnutzung.
- Exakte SKILL.md-Frontmatter-Felder gegen aktuelle claude-code-Doku (Phase 2).

## 10. Referenzdateien (bei Bedarf tief nachlesen — lokale Planungsdokumente, nicht Teil dieses Repos)
- `../2026-07-23_18_KONSOLIDIERUNG-Wissensstand.md` — alles kompakt (Black-Box).
- `../2026-07-23_16_Case-Study-1_Vertiefung.md` — APIs, Portale, Suchsyntax, verdeckter Markt.
- `../2026-07-23_19_Case-Study-2_Vertiefung_Bauspezifikation.md` — vollständige Architektur/Endpoints.
- `../2026-07-23_17_Werkstudent-Realitaet-und-Marktlage.md` — Recht/Geld/Markt.
- `data/companies_seed.csv` — 171 Firmen.
