---
name: jobsuche
description: >
  Persönliche Job-Suche: ein Lauf trägt alles Relevante zusammen (Werkstudent/
  Junior, Software/Automatisierung/Internal Tools, Raum Ulm oder Remote).
  Nutzen bei: "Jobsuche", "job digest", "neue Stellen?", "Lauf starten",
  "/jobsuche". Python holt die offenen APIs (Arbeitsagentur, Arbeitnow,
  Himalayas, Jobicy, RemoteOK, Remotive, Adzuna, LinkedIn-Guest); Claude
  scrapt Portale per Firecrawl-MCP (inkl. StepStone) und JS-Apps per
  Playwright (Indeed, GermanTechJobs, Hochschul-Portale), dann Websuche +
  Relevanz-Urteil. Ergebnis: digests/YYYY-MM-DD_digest.md + kuratierter
  Bericht. Kein Login nötig.
allowed-tools: Bash Read Grep Glob Edit Write
argument-hint: "[run|rescore|status]"
---

# Jobsuche — ein Lauf, alles Relevante

Skill-Root: `${CLAUDE_PROJECT_DIR}/jobsearch-skill/` (scripts/, config/, data/, digests/).
Details nur bei Bedarf: `${CLAUDE_PROJECT_DIR}/jobsearch-skill/IMPLEMENTATION.md`.
Arbeitsteilung: **Python = deterministisch** (APIs, Dedup, Scoring, SQLite-State),
**Claude = fuzzy** (Portale scrapen, Websuche, Relevanz beurteilen). Keine Keys.

## Ablauf (Argument leer oder `run`) — Reihenfolge einhalten

**1. Portale scrapen (Claude). Liste holen:**
```
cd "${CLAUDE_PROJECT_DIR}/jobsearch-skill" && python scripts/scrape_portals.py list
```
Die Liste hat zwei Typen:
- **`markdown`-Portale** → `firecrawl_scrape` mit `formats:["markdown"]`,
  `onlyMainContent:true`, `maxAge:0`; bei **stepstone zusätzlich `proxy:"auto"`**
  (Anti-Bot). **Tiefe:** bei stepstone Seiten 1–3 (`&page=N`), bei meinestadt
  Seiten 1–2 (`?page=N`) scrapen und die Markdown-Dateien einzeln ingesten —
  Seite 1 allein verpasst ältere, noch offene Anzeigen.
  Markdown nach `data/runs/<heute>_<portal>[_sN].md` (Write), dann:
  ```
  python scripts/scrape_portals.py ingest <portal> data/runs/<heute>_<portal>.md
  ```
- **`playwright`-Quellen** (indeed, germantechjobs, thu_jobportal, hnu_jobboerse —
  JS-Apps, Firecrawl scheitert) → `browser_navigate` auf die URL, Jobs aus der
  Seite extrahieren (Snapshot oder `browser_evaluate`), als JSON-Liste
  `[{title, company, location, url, homeoffice?, snippet?}]` nach
  `data/runs/<heute>_<name>.json` (Write), dann:
  ```
  python scripts/scrape_portals.py ingest-json <name> data/runs/<heute>_<name>.json
  ```
Eine kaputte Quelle überspringen und im Bericht erwähnen — nie den Lauf abbrechen.
Bei wenig Zeit: markdown-Portale + indeed reichen; Hochschul-Portale sind klein.

**2. API-Quellen + Digest (Python, schreibt EINEN Digest inkl. Portal-Jobs):**
```
python scripts/run.py
```
Quellen: Arbeitsagentur, Arbeitnow, Himalayas, Jobicy, RemoteOK, Remotive,
Adzuna (.env-Key), **LinkedIn (Guest-Endpoint, kein Login)** und **ats**
(verdeckter Markt: Personio/Greenhouse/Ashby/Workday/SmartRecruiters-Feeds
der Seed-Firmen aus data/companies_seed.csv).
429 bei Arbeitnow/LinkedIn = heute schon zu oft gelaufen; nicht sofort wiederholen.

**2.5 Score-Grenzfälle anreichern (Claude + enrich.py):**
```
python scripts/enrich.py list
```
Für jeden Kandidaten (Score 20–39, kein Volltext, max. 15): URL per
`firecrawl_scrape` (markdown, `onlyMainContent:true`) holen. Bei brauchbarem
Text → in Datei speichern und `python scripts/enrich.py apply <id> <datei>`.
Liefert die URL nichts Brauchbares (Login-Wall, 404, leeres Gerüst) →
`python scripts/enrich.py mark-dead <id>` — NICHT bei jedem Lauf neu versuchen.
Danach hochgerutschte Treffer in die Tagesdatei schreiben:
```
python scripts/digest.py
```
**Grenzfall-Review (immer, auch ohne Anreicherung):** Die verbliebenen 20–39er
kurz ansehen und passende im Bericht unter „Grenzfälle, trotzdem ansehen"
nennen — Python-Scores sind bei snippet-armen Quellen systematisch zu niedrig:
```
python -c "import sqlite3; c=sqlite3.connect('data/seen.sqlite'); [print(r) for r in c.execute(\"SELECT id, score, title, company, location, url FROM jobs WHERE status='new' AND score BETWEEN 20 AND 39 AND notified_at IS NULL ORDER BY score DESC LIMIT 25\")]"
```

**3. Websuche-Sweep (Claude, ergänzend):** 1–2 `firecrawl_search`-Abfragen wie
„Werkstudent Softwareentwicklung Ulm" / „working student software remote
Germany", Zeitraum letzte Woche. Funde, die NICHT im Digest stehen, im Bericht
unter „Zusätzlich gefunden (außerhalb der Pipeline)" mit Link auflisten.

**4. Relevanz-Check + Bericht (Claude).** Das Prinzip „Recall vor
Precision": Python filtert bewusst locker, DU sortierst. Im Bericht:
- **Top 3–5 Treffer** mit je 1 Satz, warum sie passen (Profil: Python/FastAPI,
  TypeScript/React/Next.js, Go, Docker, LLM-Integration; kleine Teams,
  flexible Zeiten; Details in config/profile.yaml).
- **Rauschen benennen** (Weiterbildungs-Anzeigen, Führungsrollen, Nicht-Tech) —
  im Chat markieren, NICHT aus der Digest-Datei löschen.
- Flags hervorheben: „ohne Anschreiben", Seed-Firmen (data/companies_seed.csv),
  Homeoffice. Zahlen nennen: neu/gesamt, Quellen ok/fehlgeschlagen.

## `rescore` — nach Änderungen an config/profile.yaml
```
python scripts/rescore.py
```
Manuelle Status (applied/rejected/interesting) bleiben unangetastet.

## `status` — Zustand ansehen
```
python -c "import sqlite3; c=sqlite3.connect('data/seen.sqlite'); print(c.execute('SELECT status, COUNT(*) FROM jobs GROUP BY status').fetchall()); print(c.execute('SELECT id, started, sources_ok, jobs_new, status FROM runs ORDER BY id DESC LIMIT 5').fetchall())"
```

## Status-Pflege (Feedback-Loop)
Sagt der Nutzer „beworben" / „nicht interessant" / „merken":
```
python scripts/mark.py <id> applied|rejected|interesting
python scripts/mark.py list
```
Beim Relevanz-Check `mark.py list` einbeziehen: was der Nutzer mochte/ablehnte,
schärft die Kuratierung (ähnliche Stellen hervorheben bzw. leiser behandeln).

## Wartung (ungefähr monatlich, oder wenn der Nutzer es anstößt)
```
python scripts/seed.py          # Verzeichnisse -> neue Firmen/Websites
python scripts/ats_detect.py    # neue/migrierte ATS erkennen (nur ungeprüfte)
python scripts/rescore.py       # nach Änderungen an config/profile.yaml
```

## Regeln
- Digest-Dateien sind Historie: anhängen ja, löschen/umschreiben nein.
- Änderungen an scripts/ nur testgetrieben (`python -m pytest tests/ -q`, 128 Tests).
- Keine neuen Hard-Filter in Python ohne Rückfrage (Recall vor Precision).
- Manuelle Status (applied/rejected/interesting) sind unantastbar.
