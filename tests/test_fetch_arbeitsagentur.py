"""Tests für fetch_arbeitsagentur.py — Pagination + refnr-Dedup (ohne Netz)."""
import fetch_arbeitsagentur as fa


def fake_fetch_page(pages_by_synonym):
    """Baut einen fetch_page-Ersatz: (synonym, page) -> Liste Roh-Jobs."""
    def _fetch(synonym, page):
        pages = pages_by_synonym.get(synonym, [])
        return pages[page - 1] if page <= len(pages) else []
    return _fetch


def job(refnr, titel="Werkstudent"):
    return {"refnr": refnr, "titel": titel, "arbeitgeber": "X", "arbeitsort": {"ort": "Ulm"}}


def test_paginates_while_pages_full(monkeypatch):
    monkeypatch.setattr(fa, "PAGE_SIZE", 2)
    fetch = fake_fetch_page({"syn1": [[job("a"), job("b")], [job("c")]]})
    jobs = fa.fetch_all(["syn1"], fetch_page=fetch)
    assert [j["refnr"] for j in jobs] == ["a", "b", "c"]


def test_stops_after_partial_page(monkeypatch):
    monkeypatch.setattr(fa, "PAGE_SIZE", 2)
    calls = []

    def fetch(synonym, page):
        calls.append(page)
        return [job("a")]  # kleiner als PAGE_SIZE -> letzte Seite
    fa.fetch_all(["syn1"], fetch_page=fetch)
    assert calls == [1]


def test_dedupes_refnr_across_synonyms():
    fetch = fake_fetch_page({
        "syn1": [[job("a"), job("b")]],
        "syn2": [[job("b"), job("c")]],
    })
    jobs = fa.fetch_all(["syn1", "syn2"], fetch_page=fetch)
    assert sorted(j["refnr"] for j in jobs) == ["a", "b", "c"]


def test_enrich_with_details_attaches_description_and_homeoffice():
    jobs = [job("a"), job("b")]
    details = {
        "a": {"stellenangebotsBeschreibung": "Python und Docker.", "homeofficemoeglich": True},
        "b": {},
    }
    fa.enrich_with_details(jobs, fetch_detail=lambda refnr: details[refnr])
    assert jobs[0]["_description"] == "Python und Docker."
    assert jobs[0]["_homeoffice"] is True
    assert jobs[1]["_description"] == ""
    assert jobs[1]["_homeoffice"] is False


def test_enrich_survives_detail_errors():
    jobs = [job("a")]

    def boom(refnr):
        raise RuntimeError("503")
    fa.enrich_with_details(jobs, fetch_detail=boom)
    assert jobs[0]["_description"] == ""


def test_failing_synonym_does_not_break_others():
    def fetch(synonym, page):
        if synonym == "syn1":
            raise RuntimeError("boom")
        return [job("x")] if page == 1 else []
    jobs = fa.fetch_all(["syn1", "syn2"], fetch_page=fetch)
    assert [j["refnr"] for j in jobs] == ["x"]


def test_all_synonyms_failing_raises():
    import pytest

    def fetch(synonym, page):
        raise RuntimeError("403")
    with pytest.raises(RuntimeError, match="alle 2 Synonym-Queries"):
        fa.fetch_all(["syn1", "syn2"], fetch_page=fetch)
