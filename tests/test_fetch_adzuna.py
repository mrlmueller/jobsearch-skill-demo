"""Tests für fetch_adzuna.py — env-gated, Fake-Responses (ohne Netz/Key)."""
import pytest

import fetch_adzuna as fz


def test_has_credentials_false_without_env(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    monkeypatch.setattr(fz.envutil, "load_env", lambda *a, **k: None)
    assert fz.has_credentials() is False


def test_fetch_raises_without_credentials(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    monkeypatch.setattr(fz.envutil, "load_env", lambda *a, **k: None)
    with pytest.raises(fz.MissingCredentials):
        fz.fetch()


def adzuna_result(**over):
    r = {
        "id": "12345",
        "title": "Werkstudent Softwareentwicklung (m/w/d)",
        "company": {"display_name": "Acme GmbH"},
        "location": {"display_name": "Ulm, Baden-Württemberg"},
        "redirect_url": "https://www.adzuna.de/land/ad/12345?utm_source=api",
        "description": "Python und Docker …",
        "created": "2026-07-20T08:15:00Z",
        "salary_min": None,
    }
    r.update(over)
    return r


def test_fetch_all_paginates_and_tags_source(monkeypatch):
    monkeypatch.setitem(fz.PARAMS, "results_per_page", 2)
    pages = {
        1: {"results": [adzuna_result(id="1"), adzuna_result(id="2")]},
        2: {"results": [adzuna_result(id="3")]},
        3: {"results": []},
    }
    jobs = fz.fetch_all(fetch_page=lambda p: pages[p])
    assert [j["id"] for j in jobs] == ["1", "2", "3"]
    assert all(j["_source"] == "adzuna" for j in jobs)


def test_normalize_adzuna():
    import normalize as nz
    raw = adzuna_result(_source="adzuna")
    job = nz.normalize_job(raw)
    assert job["source"] == "adzuna"
    assert job["source_job_id"] == "12345"
    assert job["company"] == "Acme GmbH"
    assert job["location"] == "Ulm, Baden-Württemberg"
    assert job["posted_at"] == "2026-07-20"
    assert job["url"].startswith("https://www.adzuna.de/land/ad/12345")
