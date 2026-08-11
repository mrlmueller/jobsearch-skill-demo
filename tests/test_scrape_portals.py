"""Tests für scrape_portals.py — Parser gegen echte Markdown-Ausschnitte (23.07.2026)."""
import scrape_portals as sp

WSJ_MD = """
### [Werkstudent DevOps & Software Engineering (w|m|d)](https://www.werkstudenten-jobs.de/jobanzeige/14033431 "Werkstudent DevOps & Software Engineering (w|m|d)")

22.07.2026 |

ADAC |

München |

Homeoffice möglich,Teilzeit

Der ADAC ist immer in Bewegung und da, um zu helfen ..

### [Werkstudent Softwareentwicklung - Industrial Engineering ..](https://www.werkstudenten-jobs.de/jobanzeige/14246734 "Werkstudent Softwareentwicklung - Industrial Engineering (w/m/d)")

22.07.2026 |

HENSOLDT |

Oberkochen |

Teilzeit

HENSOLDT ist ein führendes Unternehmen ..
"""


def test_parse_werkstudenten_jobs():
    jobs = sp.parse_werkstudenten_jobs(WSJ_MD)
    assert len(jobs) == 2
    j = jobs[0]
    assert j["title"] == "Werkstudent DevOps & Software Engineering (w|m|d)"
    assert j["company"] == "ADAC"
    assert j["location"] == "München"
    assert j["url"].endswith("/14033431")
    assert j["posted_date"] == "22.07.2026"
    assert j["homeoffice"] is True
    assert jobs[1]["homeoffice"] is False
    assert "HENSOLDT" == jobs[1]["company"]


CJ_MD = """
[### Werkstudent Software Development – Content & Automation (m/w/d)](https://www.campusjaeger.de/job/115626-werkstudent-software-development)

![Unternehmenslogo von VGL Publishing AG](https://img.campusjaeger.de/x.png)

VGL Publishing AG

Karte Indikator

Berlin

Haus

Homeoffice möglich

15–20 h pro Woche

Unterstütze unser ContentTech-Team praxisnah.

[### Werkstudent in der Softwareentwicklung (m/w/d)](https://www.campusjaeger.de/job/99700-werkstudent-in-der-softwareentwicklung)

![Unternehmenslogo von Knuddels GmbH & Co. KG](https://img.campusjaeger.de/y.png)

Knuddels GmbH & Co. KG

Karte Indikator

Karlsruhe

10–20 h pro Woche

15–18 € pro Stunde

Bewirb dich initiativ.

[TMG Technologie und Engineering GmbH](https://www.campusjaeger.de/unternehmen/1982)
"""


def test_parse_campusjaeger():
    jobs = sp.parse_campusjaeger(CJ_MD)
    assert len(jobs) == 2          # Unternehmens-Link ist KEIN Job
    assert jobs[0]["company"] == "VGL Publishing AG"
    assert jobs[0]["location"] == "Berlin"
    assert jobs[0]["homeoffice"] is True
    assert jobs[1]["company"] == "Knuddels GmbH & Co. KG"
    assert jobs[1]["salary"] == "15–18 € pro Stunde"
    assert jobs[1]["homeoffice"] is False


MS_MD = """
*   ![Werkstudent Agentic AI & Multi-Agent-Systeme (d/m/w/x)](https://image-resize.meinestadt.de/x.gif "Werkstudent Agentic AI")

    [### Werkstudent Agentic AI & Multi-Agent-Systeme (d/m/w/x)](https://www.meinestadt.de/ulm/redirect/jobs-redirect?redirectUrl=abc&id=100013543610 "Werkstudent Agentic AI & Multi-Agent-Systeme (d/m/w/x)")

    Mercedes-Benz Tech Innovation

    Ulm

    23.07.2026

    Flexible Arbeitszeiten

    Machine Learning

    Python

    \\+ XX Weitere

*   ![Postbote für Briefe (m/w/d)](https://image-resize.meinestadt.de/y.jpg "Postbote")

    [### Postbote für Briefe (m/w/d)](https://jobs.meinestadt.de/ulm/premium?id=100012875447 "Postbote für Briefe (m/w/d)")

    Deutsche Post AG

    Ulm

    16.07.2026

    Job-Rad
"""


def test_parse_meinestadt():
    jobs = sp.parse_meinestadt(MS_MD)
    assert len(jobs) == 2
    assert jobs[0]["title"].startswith("Werkstudent Agentic AI")
    assert jobs[0]["company"] == "Mercedes-Benz Tech Innovation"
    assert jobs[0]["location"] == "Ulm"
    assert jobs[0]["posted_date"] == "23.07.2026"
    assert jobs[1]["company"] == "Deutsche Post AG"


def test_role_filter_drops_postbote():
    jobs = sp.parse_meinestadt(MS_MD)
    kept = sp.filter_jobs(jobs)
    assert len(kept) == 1
    assert kept[0]["title"].startswith("Werkstudent Agentic AI")
    assert kept[0]["_source"] == "portal_meinestadt"


def test_normalize_portal_job():
    import normalize as nz
    raw = {"title": "Werkstudent Dev", "company": "Acme", "location": "Ulm",
           "url": "https://x.de/1", "posted_date": "22.07.2026",
           "homeoffice": True, "salary": None, "snippet": "Python und Docker",
           "_source": "portal_werkstudenten_jobs"}
    job = nz.normalize_job(raw)
    assert job["source"] == "portal_werkstudenten_jobs"
    assert job["posted_at"] == "2026-07-22"
    assert job["remote"] is True
    assert "python" in job["tech_tags"]


SS_MD = """
[![HENSOLDT](<Base64-Image-Removed>)](https://www.stepstone.de/cmp/de/hensoldt-173428/jobs)

[Werkstudent Softwareentwicklung - Industrial Engineering (w/m/d)](https://www.stepstone.de/stellenangebote--Werkstudent-Softwareentwicklung-Industrial-Engineering-w-m-d-Oberkochen-HENSOLDT--14246734-inline.html)

---------------------------------------------------------------------

HENSOLDT

Oberkochen

HENSOLDT ist ein führendes Unternehmen der europäischen Verteidigungsindustrie.

[![d-fine](<Base64-Image-Removed>)](https://www.stepstone.de/cmp/de/d-fine/jobs)

[Werkstudent (m/w/d) Softwareentwicklung](https://www.stepstone.de/stellenangebote--Werkstudent-m-w-d-Softwareentwicklung-Home-Office-d-fine-GmbH--14308695-inline.html)

------------------------------------------------------------------

d-fine GmbH

Berlin, Stuttgart, Home-Office

d-fine ist ein europäisches Beratungsunternehmen mit Python und Cloud-Fokus.
"""


def test_parse_stepstone():
    jobs = sp.parse_stepstone(SS_MD)
    assert len(jobs) == 2
    assert jobs[0]["title"].startswith("Werkstudent Softwareentwicklung - Industrial")
    assert jobs[0]["company"] == "HENSOLDT"
    assert jobs[0]["location"] == "Oberkochen"
    assert jobs[0]["url"].endswith("14246734-inline.html")
    assert jobs[0]["homeoffice"] is False
    assert jobs[1]["company"] == "d-fine GmbH"
    assert jobs[1]["homeoffice"] is True          # Home-Office im Ort


ABS_MD = r"""
Bei Enter auf eine Anzeige werden Details nebenan dargestellt.*   [![Seifert Logistics Group Logo](https://uno-production.imgix.net/logo.png)\
    \
    PRAKTIKANT / WERKSTUDENT TENDER MANAGEMENT & LOGISTIK (M/W/D)\
    -------------------------------------------------------------\
    \
    Seifert Logistics Group\
    \
    PRAKTIKANT / WERKSTUDENT TENDER MANAGEMENT & LOGISTIK (M/W/D)\
    -------------------------------------------------------------\
    \
    *   Standort Ulm\
    \
    Neu Homeoffice möglich](https://www.absolventa.de/stellenangebote/12838420-b-praktikant-werkstudent-tender-management-logistik-m-w-d)
"""


def test_parse_absolventa():
    jobs = sp.parse_absolventa(ABS_MD)
    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "PRAKTIKANT / WERKSTUDENT TENDER MANAGEMENT & LOGISTIK (M/W/D)"
    assert j["company"] == "Seifert Logistics Group"
    assert j["location"] == "Ulm"
    assert j["homeoffice"] is True
    assert j["url"].endswith("tender-management-logistik-m-w-d")


GIT_MD = r"""
[![DATEV eG](<Base64-Image-Removed>)\
\
DATEV eG\
\
Werkstudent Testautomatisierung für Finanz- und Beschaffungsprozesse (m/w/d)\
\
Quality Assurance +1\
\
Nürnberg\
\
Home-Office](https://www.get-in-it.de/jobsuche/p310352?start=0&limit=39&ref=Jobsuche)

[![Hahn Gruppe](<Base64-Image-Removed>)\
\
Tipp\
\
Hahn Gruppe\
\
Systemadministrator (m/w/d)\
\
System Engineering / Admin\
\
Bergisch Gladbach](https://www.get-in-it.de/jobsuche/p310377?start=0&limit=39&ref=Jobsuche)
"""


def test_parse_get_in_it():
    jobs = sp.parse_get_in_it(GIT_MD)
    assert len(jobs) == 2
    assert jobs[0]["company"] == "DATEV eG"
    assert jobs[0]["title"].startswith("Werkstudent Testautomatisierung")
    assert jobs[0]["location"] == "Nürnberg"
    assert jobs[0]["homeoffice"] is True
    assert jobs[1]["company"] == "Hahn Gruppe"       # "Tipp"-Badge übersprungen
    assert jobs[1]["title"] == "Systemadministrator (m/w/d)"
    assert jobs[1]["homeoffice"] is False


def test_ingest_json_upserts(tmp_path):
    """Für Quellen ohne deterministischen Parser (z. B. Indeed via Playwright):
    Claude extrahiert selbst und übergibt JSON."""
    import json
    import store
    conn = store.init_db(tmp_path / "s.sqlite")
    payload = [
        {"title": "Werkstudent Software Testing (m/w/d)", "company": "Bosch Group",
         "location": "Ulm", "url": "https://de.indeed.com/viewjob?jk=abc",
         "homeoffice": True, "snippet": "Python und Docker im Testumfeld"},
        {"title": "Verkäufer (m/w/d)", "company": "X", "location": "Ulm",
         "url": "https://de.indeed.com/viewjob?jk=def"},
    ]
    stats = sp.ingest_json(conn, "indeed", payload)
    assert stats["kept"] == 1 and stats["new"] == 1     # Verkäufer fällt raus
    row = conn.execute("SELECT source, remote FROM jobs").fetchone()
    assert row[0] == "portal_indeed" and row[1] == 1
    conn.close()


def test_ingest_markdown_upserts_scored_jobs(tmp_path):
    """Claude scrapt per MCP, ingest_markdown parst+bewertet+speichert."""
    import store
    conn = store.init_db(tmp_path / "s.sqlite")
    stats = sp.ingest_markdown(conn, "meinestadt", MS_MD)
    assert stats["parsed"] == 2          # beide Anzeigen erkannt
    assert stats["kept"] == 1            # Postbote fällt am Rollen-Filter
    assert stats["new"] == 1
    row = conn.execute("SELECT title, source, status FROM jobs").fetchone()
    assert row[0].startswith("Werkstudent Agentic AI")
    assert row[1] == "portal_meinestadt"
    # zweiter Ingest desselben Markdowns: kein Duplikat
    stats2 = sp.ingest_markdown(conn, "meinestadt", MS_MD)
    assert stats2["new"] == 0
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    conn.close()


def test_unknown_portal_raises(tmp_path):
    import pytest
    import store
    conn = store.init_db(tmp_path / "s.sqlite")
    with pytest.raises(KeyError):
        sp.ingest_markdown(conn, "gibtsnicht", "x")
    conn.close()
