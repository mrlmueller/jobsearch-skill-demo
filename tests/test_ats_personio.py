"""Tests für ats_personio.py — Personio-XML-Adapter (Felder lt. Spez §3)."""
import ats_personio as ap

XML = """<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
  <position>
    <id>1234567</id>
    <office>Ulm</office>
    <department>Engineering</department>
    <name>Werkstudent Softwareentwicklung (m/w/d)</name>
    <employmentType>intern</employmentType>
    <schedule>part-time</schedule>
    <seniority>student</seniority>
    <yearsOfExperience>lt-1</yearsOfExperience>
    <keywords>python,react</keywords>
    <createdAt>2026-07-10T08:00:00+02:00</createdAt>
    <jobDescriptions>
      <jobDescription>
        <name>Deine Aufgaben</name>
        <value><![CDATA[<p>Du entwickelst mit <b>Python</b> und Docker interne Tools.</p>]]></value>
      </jobDescription>
      <jobDescription>
        <name>Dein Profil</name>
        <value><![CDATA[<ul><li>Studium Informatik</li></ul>]]></value>
      </jobDescription>
    </jobDescriptions>
  </position>
  <position>
    <id>999</id>
    <office>München</office>
    <name>Senior Architect (m/w/d)</name>
    <employmentType>permanent</employmentType>
    <schedule>full-time</schedule>
    <seniority>senior</seniority>
    <createdAt>2026-07-01T08:00:00+02:00</createdAt>
    <jobDescriptions/>
  </position>
</workzag-jobs>
"""


def test_parse_xml_extracts_positions():
    jobs = ap.parse_xml(XML, slug="acme", company="Acme GmbH")
    assert len(jobs) == 2
    j = jobs[0]
    assert j["title"] == "Werkstudent Softwareentwicklung (m/w/d)"
    assert j["company"] == "Acme GmbH"
    assert j["location"] == "Ulm"
    assert j["employment_hint"] == "intern"
    assert j["schedule"] == "part-time"
    assert j["posted_at"] == "2026-07-10"
    assert "Python" in j["description"] and "<p>" not in j["description"]
    assert "Studium Informatik" in j["description"]
    assert j["url"] == "https://acme.jobs.personio.de/job/1234567"
    assert j["_source"] == "ats_personio"


def test_fetch_company_migrated_307(monkeypatch):
    class FakeResponse:
        status_code = 307
        text = ""

        def raise_for_status(self):
            pass
    monkeypatch.setattr(ap.httpx, "get", lambda *a, **k: FakeResponse())
    result = ap.fetch_company("acme", "Acme GmbH")
    assert result == "migrated"


def test_fetch_company_404_is_gone(monkeypatch):
    class FakeResponse:
        status_code = 404
        text = ""
    monkeypatch.setattr(ap.httpx, "get", lambda *a, **k: FakeResponse())
    assert ap.fetch_company("acme", "Acme GmbH") == "gone"


def test_fetch_company_ok(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = XML
    monkeypatch.setattr(ap.httpx, "get", lambda *a, **k: FakeResponse())
    jobs = ap.fetch_company("acme", "Acme GmbH")
    assert isinstance(jobs, list) and len(jobs) == 2


def test_normalize_ats_personio():
    import normalize as nz
    raw = ap.parse_xml(XML, slug="acme", company="Acme GmbH")[0]
    job = nz.normalize_job(raw)
    assert job["source"] == "ats_personio"
    assert job["source_job_id"] == "1234567"
    assert job["title"].startswith("Werkstudent")
    assert job["employment_type"] == "werkstudent"   # intern+student+part-time ~ werkstudent-Kontext
    assert "python" in job["tech_tags"] and "docker" in job["tech_tags"]
    assert job["posted_at"] == "2026-07-10"
