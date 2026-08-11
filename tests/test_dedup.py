"""Tests für dedup.py — URL-Kanonisierung, Fingerprint, Fuzzy-Duplikate."""
import dedup


def test_canonicalize_url_strips_tracking():
    url = "https://example.com/job/1?utm_source=x&utm_medium=y&ref=abc&id=7#apply"
    assert dedup.canonicalize_url(url) == "https://example.com/job/1?id=7"


def test_canonicalize_url_plain_stays():
    assert dedup.canonicalize_url("https://example.com/job/1") == "https://example.com/job/1"


def test_fingerprint_same_job_two_sources():
    """Dieselbe Stelle aus 2 Quellen -> gleicher Hash (Manifest-TEST)."""
    h1 = dedup.fingerprint("Liebherr-Mischtechnik GmbH",
                           "Werkstudent Softwareentwicklung (m/w/d)",
                           "88427 Bad Schussenried")
    h2 = dedup.fingerprint("Liebherr-Mischtechnik",
                           "Werkstudent Softwareentwicklung",
                           "Bad Schussenried")
    assert h1 == h2


def test_fingerprint_umlaut_normalization():
    assert dedup.fingerprint("Jäger AG", "Entwickler", "Günzburg") == \
           dedup.fingerprint("Jaeger", "Entwickler", "Guenzburg")


def test_fingerprint_different_jobs_differ():
    h1 = dedup.fingerprint("Acme GmbH", "Werkstudent Frontend", "Ulm")
    h2 = dedup.fingerprint("Acme GmbH", "Werkstudent Backend", "Ulm")
    assert h1 != h2


def test_fuzzy_is_dup_near_identical():
    a = {"title": "Werkstudent*in Softwareentwicklung", "company": "Acme Solutions GmbH"}
    b = {"title": "Werkstudent Softwareentwicklung", "company": "Acme Solutions"}
    assert dedup.fuzzy_is_dup(a, b) is True


def test_fuzzy_is_dup_different_company():
    a = {"title": "Werkstudent Softwareentwicklung", "company": "Acme GmbH"}
    b = {"title": "Werkstudent Softwareentwicklung", "company": "Globex AG"}
    assert dedup.fuzzy_is_dup(a, b) is False


def test_dedup_all_merges_and_keeps_distinct():
    jobs = [
        {"title": "Werkstudent Software (m/w/d)", "company": "Acme GmbH",
         "location": "89073 Ulm", "url": "https://a.de/1?utm_source=feed"},
        {"title": "Werkstudent Software", "company": "Acme",
         "location": "Ulm", "url": "https://b.de/1"},
        {"title": "Junior Developer", "company": "Globex AG",
         "location": "Augsburg", "url": "https://c.de/2"},
    ]
    result = dedup.dedup_all(jobs)
    assert len(result) == 2
    assert all(j["dedup_hash"] for j in result)
    assert result[0]["canonical_url"] == "https://a.de/1"
