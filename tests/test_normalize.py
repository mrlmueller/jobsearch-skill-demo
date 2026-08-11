"""Tests für normalize.py — beide Quellen → einheitliches Schema."""
import normalize as nz

ANCHORS = ["python", "go", "next.js", "ci/cd", "docker", "react"]


def test_extract_tech_tags_word_boundaries():
    text = "Wir nutzen Python, Go und Next.js mit CI/CD. Google Analytics."
    assert nz.extract_tech_tags(text, ANCHORS) == ["python", "go", "next.js", "ci/cd"]


def test_extract_tech_tags_no_false_positive_in_words():
    assert nz.extract_tech_tags("Google Golang-frei, Reaktion", ANCHORS) == []


def test_normalize_arbeitsagentur():
    raw = {
        "beruf": "Softwareentwickler/in",
        "titel": "Werkstudent Softwareentwicklung (m/w/d)",
        "refnr": "123-456-S",
        "arbeitsort": {"plz": "89073", "ort": "Ulm", "region": "BW"},
        "arbeitgeber": "Acme GmbH",
        "aktuelleVeroeffentlichungsdatum": "2026-07-13",
        "_source": "arbeitsagentur",
        "_url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/123-456-S",
    }
    job = nz.normalize_job(raw)
    assert job["source"] == "arbeitsagentur"
    assert job["source_job_id"] == "123-456-S"
    assert job["title"] == "Werkstudent Softwareentwicklung (m/w/d)"
    assert job["company"] == "Acme GmbH"
    assert job["location"] == "Ulm"
    assert job["remote"] is False
    assert job["posted_at"] == "2026-07-13"
    assert job["employment_type"] == "werkstudent"
    assert job["url"].endswith("123-456-S")
    assert isinstance(job["raw_json"], str)


def test_normalize_himalayas():
    raw = {
        "title": "Junior Fullstack Developer", "companyName": "AgilityFeat",
        "locationRestrictions": ["Germany"], "employmentType": "Full Time",
        "description": "<p>React und Docker</p>", "pubDate": 1784739785,
        "applicationLink": "https://himalayas.app/companies/agilityfeat/jobs/x",
        "guid": "hima-guid-1", "_source": "himalayas",
    }
    job = nz.normalize_job(raw)
    assert job["source"] == "himalayas"
    assert job["source_job_id"] == "hima-guid-1"
    assert job["remote"] is True
    assert job["location"] == "Remote (Germany)"
    assert job["posted_at"] == "2026-07-22"
    assert "react" in job["tech_tags"] and "docker" in job["tech_tags"]


def test_normalize_jobicy():
    raw = {
        "id": "144336", "jobTitle": "Junior Go Developer", "companyName": "Kraken",
        "jobGeo": "Germany", "jobLevel": "Entry", "jobType": "['Full-Time']",
        "url": "https://jobicy.com/jobs/144336", "salary": None,
        "jobDescription": "<p>Go und Docker</p>",
        "pubDate": "2026-07-22T18:40:10+00:00", "_source": "jobicy",
    }
    job = nz.normalize_job(raw)
    assert job["source"] == "jobicy"
    assert job["source_job_id"] == "144336"
    assert job["remote"] is True
    assert job["posted_at"] == "2026-07-22"
    assert "go" in job["tech_tags"]


def test_normalize_remoteok():
    raw = {"id": 1135294, "position": "Junior Backend Developer", "company": "Acme",
           "location": "Worldwide", "tags": ["python", "docker"],
           "date": "2026-07-23T07:31:34+00:00",
           "url": "https://remoteOK.com/remote-jobs/x", "description": "Python",
           "salary_min": 40000, "salary_max": 60000, "_source": "remoteok"}
    job = nz.normalize_job(raw)
    assert job["source"] == "remoteok"
    assert job["source_job_id"] == "1135294"
    assert job["remote"] is True
    assert job["posted_at"] == "2026-07-23"
    assert "python" in job["tech_tags"]
    assert "40000" in job["salary"]


def test_normalize_remotive():
    raw = {"id": 9, "title": "Junior Software Engineer", "company_name": "X",
           "candidate_required_location": "Europe", "job_type": "full_time",
           "publication_date": "2026-07-22T06:22:11",
           "url": "https://remotive.com/j/9", "description": "<p>Go und Docker</p>",
           "salary": "", "_source": "remotive"}
    job = nz.normalize_job(raw)
    assert job["source"] == "remotive"
    assert job["remote"] is True
    assert job["location"] == "Remote (Europe)"
    assert job["posted_at"] == "2026-07-22"
    assert "go" in job["tech_tags"]


def test_normalize_arbeitnow():
    raw = {
        "slug": "dev-x-1", "company_name": "Startup GmbH",
        "title": "Working Student Software Development",
        "description": "<p>Wir suchen dich! <b>Python</b> und Docker.</p>",
        "remote": True, "url": "https://www.arbeitnow.com/jobs/companies/s/dev-x-1",
        "tags": ["Software Development"], "job_types": ["Werkstudent"],
        "location": "Berlin", "created_at": 1784831431,
        "_source": "arbeitnow",
    }
    job = nz.normalize_job(raw)
    assert job["source"] == "arbeitnow"
    assert job["source_job_id"] == "dev-x-1"
    assert job["remote"] is True
    assert job["posted_at"] == "2026-07-23"          # aus Unix-Timestamp
    assert "Python" in job["description"] and "<p>" not in job["description"]
    assert job["employment_type"] == "werkstudent"
    assert set(job["tech_tags"]) == {"python", "docker"}
