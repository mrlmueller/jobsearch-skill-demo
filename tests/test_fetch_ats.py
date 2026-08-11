"""Tests für fetch_ats.py — CSV-getriebener Dispatch an die ATS-Adapter."""
import fetch_ats as fa


def rows(*specs):
    base = {"name": "", "ats_type": "", "ats_slug": "", "website": ""}
    return [{**base, **s} for s in specs]


def test_dispatch_personio_and_cleanjson(monkeypatch):
    calls = []
    monkeypatch.setattr(fa.ats_personio, "fetch_company",
                        lambda slug, company: calls.append(("personio", slug))
                        or [{"_source": "ats_personio", "title": "A"}])
    monkeypatch.setattr(fa.ats_cleanjson, "fetch_company",
                        lambda t, slug, company: calls.append((t, slug))
                        or [{"_source": f"ats_{t}", "title": "B"}])
    monkeypatch.setattr(fa.time, "sleep", lambda s: None)
    data = rows(
        {"name": "Acme", "ats_type": "personio", "ats_slug": "acme"},
        {"name": "Beta", "ats_type": "greenhouse", "ats_slug": "beta"},
        {"name": "NoAts", "ats_type": "", "ats_slug": ""},
        {"name": "TT", "ats_type": "teamtailor", "ats_slug": "tt"},  # kein Feed -> skip
    )
    jobs = fa.fetch_from_rows(data)
    assert ("personio", "acme") in calls
    assert ("greenhouse", "beta") in calls
    assert len(jobs) == 2


def test_personio_migrated_flagged_without_disk_write(monkeypatch, tmp_path):
    monkeypatch.setattr(fa.ats_personio, "fetch_company",
                        lambda slug, company: "migrated")
    monkeypatch.setattr(fa.time, "sleep", lambda s: None)
    # Wache: fetch_from_rows darf NIE speichern (Regression 2026-07-24)
    monkeypatch.setattr(fa.seed, "save_rows",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("fetch_from_rows darf nicht speichern")))
    data = rows({"name": "TestFirma", "ats_type": "personio", "ats_slug": "testfirma"})
    jobs = fa.fetch_from_rows(data)
    assert jobs == []
    assert data[0]["scrape_status"] == "migrated"   # für ats_detect-Nachprüfung


def test_save_rows_refuses_stub_data(tmp_path):
    import pytest
    import seed
    with pytest.raises(ValueError):
        seed.save_rows([{"name": "x", "ats_type": "personio"}])
