"""Tests für fetch_arbeitnow.py — client-seitiger Filter + Pagination (ohne Netz)."""
import fetch_arbeitnow as fan

REGIONS = ["Ulm", "Neu-Ulm", "Günzburg", "Augsburg"]


def job(**over):
    j = {
        "slug": "x", "company_name": "Acme", "title": "Werkstudent Softwareentwicklung",
        "description": "<p>Python</p>", "remote": False,
        "url": "https://arbeitnow.com/jobs/x", "tags": [], "job_types": [],
        "location": "Ulm", "created_at": 1784831431,
    }
    j.update(over)
    return j


def test_matching_title_and_location_passes():
    assert fan.matches_profile(job(), REGIONS) is True


def test_role_mismatch_fails():
    assert fan.matches_profile(job(title="E-Commerce Manager (m/w/d)"), REGIONS) is False


def test_remote_overrides_location():
    assert fan.matches_profile(
        job(title="Junior Developer", location="Berlin", remote=True), REGIONS) is True


def test_wrong_city_not_remote_fails():
    assert fan.matches_profile(
        job(title="Junior Developer", location="Berlin", remote=False), REGIONS) is False


def test_role_match_via_tags():
    assert fan.matches_profile(
        job(title="Coding Enthusiast (m/w/d)", tags=["Software Development"]), REGIONS) is True


def test_fetch_all_paginates_and_filters():
    pages = {
        1: {"data": [job(slug="a"), job(slug="b", title="Vertriebsmitarbeiter")],
            "links": {"next": "…page=2"}},
        2: {"data": [job(slug="c", title="Junior Software Engineer")],
            "links": {"next": None}},
    }
    jobs = fan.fetch_all(REGIONS, fetch_page=lambda p: pages[p])
    assert [j["slug"] for j in jobs] == ["a", "c"]
