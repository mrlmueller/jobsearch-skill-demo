"""Tests für score.py — Stufe-0-Regeln aus profile.yaml."""
import pytest

import score as sc


@pytest.fixture(autouse=True)
def _no_real_seed_csv(monkeypatch):
    """Tests dürfen nicht von der echten companies_seed.csv abhängen."""
    monkeypatch.setattr(sc, "load_seed_companies", lambda: ())

PROFILE = {
    "person": {"regions_in_radius": ["Ulm", "Neu-Ulm", "Augsburg"], "remote_ok": True},
    "must": {
        "employment_types": ["werkstudent", "teilzeit", "praktikum",
                             "working student", "part-time", "intern"],
        "role_is_tech": True,
        "location_in_radius_or_remote": True,
    },
    "plus": {
        "tech_tag_match": 10,
        "startup_or_small_team": 15,
        "ki_affine_firma": 15,
        "no_cover_letter_or_takehome": 10,
        "flexible_hours_or_remote": 10,
        "uebernahme_perspektive": 10,
        "from_companies_seed": 10,
    },
    "minus_flags": {"live_leetcode_signal": -5, "konzern_massenprozess": -5},
    "exclude_keywords": ["senior", "lead", "principal", "teamleiter", "(m/w/d) Vertrieb"],
}


def job(**over):
    j = {
        "title": "Werkstudent Softwareentwicklung (m/w/d)",
        "company": "Acme GmbH",
        "location": "Ulm",
        "remote": False,
        "description": "Python und Docker in kleinem Team. Flexible Arbeitszeiten.",
        "tech_tags": ["python", "docker"],
        "employment_type": "werkstudent",
        "status": "new",
    }
    j.update(over)
    return j


def test_good_job_scores_and_stays_new():
    j = sc.score_job(job(), PROFILE)
    # 2 Tech-Tags (20) + kleines Team (15) + flexibel (10) = 45
    assert j["status"] == "new"
    assert j["score"] == 45
    assert "tech" in j["score_reason"].lower()


def test_non_tech_role_ignored():
    j = sc.score_job(job(title="Werkstudent Vertrieb", tech_tags=[],
                         description="Kunden anrufen."), PROFILE)
    assert j["status"] == "ignored"


def test_out_of_radius_not_remote_ignored():
    j = sc.score_job(job(location="Berlin", remote=False), PROFILE)
    assert j["status"] == "ignored"


def test_remote_out_of_radius_ok():
    j = sc.score_job(job(location="Berlin", remote=True), PROFILE)
    assert j["status"] == "new"


def test_exclude_keyword_senior_ignored():
    j = sc.score_job(job(title="Senior Software Engineer (m/w/d)"), PROFILE)
    assert j["status"] == "ignored"


def test_wrong_employment_type_ignored():
    j = sc.score_job(job(title="Softwareentwickler Vollzeit unbefristet",
                         employment_type="vollzeit"), PROFILE)
    assert j["status"] == "ignored"


def test_junior_title_without_detected_type_passes():
    j = sc.score_job(job(title="Junior Software Engineer",
                         employment_type=None), PROFILE)
    assert j["status"] == "new"


def test_nontech_title_with_one_tag_ignored():
    """Regression: 'Film & Festival Operations' darf nicht als Tech-Rolle zählen."""
    j = sc.score_job(job(title="Werkstudent:in Film & Festival Operations",
                         tech_tags=["ki"],
                         description="Startup, flexible Arbeitszeiten, KI-Tools."),
                     PROFILE)
    assert j["status"] == "ignored"


def test_nontech_title_with_three_tags_passes():
    j = sc.score_job(job(title="Werkstudent Digitalisierung",
                         tech_tags=["python", "docker", "react"]), PROFILE)
    assert j["status"] == "new"


def test_seed_company_bonus():
    base = sc.score_job(job(), PROFILE)["score"]
    seeded = sc.score_job(job(), PROFILE, seed_companies=["acme gmbh"])["score"]
    assert seeded == base + 10


def test_minus_flag_leetcode():
    j = sc.score_job(job(description="Python, Docker, kleines Team, flexible "
                                     "Arbeitszeiten. Live-Coding-Challenge im Prozess."),
                     PROFILE)
    assert j["score"] == 40  # 45 - 5
    assert "live" in j["score_reason"].lower()


def test_score_clamped_0_100():
    j = sc.score_job(job(tech_tags=["a"] * 20), PROFILE)
    assert 0 <= j["score"] <= 100
