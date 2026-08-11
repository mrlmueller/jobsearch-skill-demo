"""Tests für fetch_remote.py — Himalayas + Jobicy (ohne Netz)."""
import fetch_remote as fr


def hima_job(**over):
    j = {
        "title": "Junior Fullstack Developer", "companyName": "Acme",
        "locationRestrictions": [], "seniority": ["Entry-level"],
        "employmentType": "Full Time", "description": "Python", "excerpt": "…",
        "applicationLink": "https://himalayas.app/companies/acme/jobs/x",
        "guid": "hima-1", "pubDate": 1784739785,
    }
    j.update(over)
    return j


def test_himalayas_no_restrictions_passes():
    assert fr.himalayas_ok(hima_job()) is True


def test_himalayas_germany_restriction_passes():
    assert fr.himalayas_ok(hima_job(locationRestrictions=["Germany", "Austria"])) is True


def test_himalayas_foreign_restriction_fails():
    assert fr.himalayas_ok(hima_job(locationRestrictions=["Colombia"])) is False


def test_himalayas_non_tech_role_fails():
    assert fr.himalayas_ok(hima_job(title="Sales Manager DACH")) is False


def jobicy_job(**over):
    j = {
        "id": "1", "jobTitle": "Junior Software Engineer", "companyName": "X",
        "jobLevel": "Entry", "jobGeo": "Germany", "jobType": "['Full-Time']",
        "url": "https://jobicy.com/jobs/1", "jobDescription": "<p>Go</p>",
        "pubDate": "2026-07-22T18:40:10+00:00",
    }
    j.update(over)
    return j


def test_jobicy_tech_role_passes():
    assert fr.jobicy_ok(jobicy_job()) is True


def test_jobicy_non_tech_fails():
    assert fr.jobicy_ok(jobicy_job(jobTitle="Content Marketing Manager")) is False


def remoteok_job(**over):
    j = {"id": "1135294", "position": "Junior Backend Developer", "company": "Acme",
         "location": "Worldwide", "tags": ["dev", "python"], "date": "2026-07-23T07:31:34+00:00",
         "url": "https://remoteOK.com/remote-jobs/x", "description": "Python",
         "salary_min": 0, "salary_max": 0}
    j.update(over)
    return j


def test_remoteok_worldwide_tech_passes():
    assert fr.remoteok_ok(remoteok_job()) is True


def test_remoteok_foreign_only_fails():
    assert fr.remoteok_ok(remoteok_job(location="Toronto, Ontario, Canada")) is False


def test_remoteok_non_tech_fails():
    assert fr.remoteok_ok(remoteok_job(position="Concept Artist", tags=["design"])) is False


def test_fetch_remoteok_skips_legal_entry():
    payload = [{"last_updated": 1, "legal": "…"}, remoteok_job()]
    jobs = fr.fetch_remoteok(fetch_fn=lambda: payload)
    assert len(jobs) == 1 and jobs[0]["_source"] == "remoteok"


def remotive_job(**over):
    j = {"id": 9, "title": "Junior Software Engineer", "company_name": "X",
         "candidate_required_location": "Worldwide", "job_type": "full_time",
         "publication_date": "2026-07-22T06:22:11", "url": "https://remotive.com/j/9",
         "description": "<p>Go</p>", "salary": "", "tags": []}
    j.update(over)
    return j


def test_remotive_worldwide_passes():
    assert fr.remotive_ok(remotive_job()) is True


def test_remotive_usa_only_fails():
    assert fr.remotive_ok(remotive_job(candidate_required_location="USA Only")) is False


def test_fetch_remotive_filters_and_tags():
    payload = {"jobs": [remotive_job(), remotive_job(id=10, title="Sales Manager")]}
    jobs = fr.fetch_remotive(fetch_fn=lambda: payload)
    assert len(jobs) == 1 and jobs[0]["_source"] == "remotive"


def test_fetch_himalayas_dedupes_guid_across_queries():
    payloads = {
        "working student": {"jobs": [hima_job(guid="a")]},
        "junior developer": {"jobs": [hima_job(guid="a"), hima_job(guid="b")]},
    }
    jobs = fr.fetch_himalayas(["working student", "junior developer"],
                              fetch_query=lambda q: payloads[q])
    assert sorted(j["guid"] for j in jobs) == ["a", "b"]
    assert all(j["_source"] == "himalayas" for j in jobs)
