"""Tests für fetch_linkedin.py — Guest-Endpoint-Parser (echte Card-Struktur 2026-07-24)."""
import fetch_linkedin as fl

CARD_HTML = """
<li>
  <div class="base-card base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:4426792114">
    <a class="base-card__full-link" href="https://de.linkedin.com/jobs/view/werkstudent-softwareentwicklung-quality-engineering-m-w-d-at-wilken-software-group-4426792114?position=1&amp;refId=xyz">
      <span class="sr-only">WERKSTUDENT SOFTWAREENTWICKLUNG &amp; QUALITY ENGINEERING (M/W/D)</span>
    </a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">
        WERKSTUDENT SOFTWAREENTWICKLUNG &amp; QUALITY ENGINEERING (M/W/D)
      </h3>
      <h4 class="base-search-card__subtitle">
        <a class="hidden-nested-link" href="https://de.linkedin.com/company/wilken-software-group">
          Wilken Software Group
        </a>
      </h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">Ulm</span>
        <time class="job-search-card__listdate" datetime="2026-07-21">vor 3 Tagen</time>
      </div>
    </div>
  </div>
</li>
<li>
  <div class="base-card job-search-card" data-entity-urn="urn:li:jobPosting:999">
    <a class="base-card__full-link" href="https://de.linkedin.com/jobs/view/other-999?x=1">
      <span class="sr-only">Junior Developer</span>
    </a>
    <h3 class="base-search-card__title">Junior Developer</h3>
    <h4 class="base-search-card__subtitle"><a href="#">Acme GmbH</a></h4>
    <span class="job-search-card__location">Stuttgart</span>
  </div>
</li>
"""


def test_parse_cards_extracts_fields():
    jobs = fl.parse_cards(CARD_HTML)
    assert len(jobs) == 2
    j = jobs[0]
    assert j["job_id"] == "4426792114"
    assert j["title"] == "WERKSTUDENT SOFTWAREENTWICKLUNG & QUALITY ENGINEERING (M/W/D)"
    assert j["company"] == "Wilken Software Group"
    assert j["location"] == "Ulm"
    assert j["posted_at"] == "2026-07-21"
    # URL kanonisch ohne Tracking-Query
    assert j["url"] == ("https://de.linkedin.com/jobs/view/"
                        "werkstudent-softwareentwicklung-quality-engineering-m-w-d-"
                        "at-wilken-software-group-4426792114")
    assert jobs[1]["posted_at"] is None


def test_fetch_all_paginates_and_dedupes():
    pages = {
        ("q1", 0): CARD_HTML,      # 2 Cards
        ("q1", 10): "",            # leer -> Ende
        ("q2", 0): CARD_HTML,      # gleiche IDs -> Duplikate
        ("q2", 10): "",
    }
    jobs = fl.fetch_all(["q1", "q2"], fetch_page=lambda q, s: pages[(q, s)])
    assert len(jobs) == 2
    assert all(j["_source"] == "linkedin" for j in jobs)


def test_failing_query_does_not_break_others():
    def fetch(q, start):
        if q == "q1":
            raise RuntimeError("429")
        return CARD_HTML if start == 0 else ""
    jobs = fl.fetch_all(["q1", "q2"], fetch_page=fetch)
    assert len(jobs) == 2


def test_normalize_linkedin():
    import normalize as nz
    raw = fl.parse_cards(CARD_HTML)[0]
    raw["_source"] = "linkedin"
    job = nz.normalize_job(raw)
    assert job["source"] == "linkedin"
    assert job["source_job_id"] == "4426792114"
    assert job["company"] == "Wilken Software Group"
    assert job["location"] == "Ulm"
    assert job["posted_at"] == "2026-07-21"
    assert job["remote"] is False
