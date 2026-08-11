"""Tests für seed.py — Verzeichnisse → companies_seed.csv anreichern."""
import seed


WIKI_CONTENT = """{{Vorlage:Textbox
 | Logo=[[File:Akkodis Logo 400x50.png|center|150px]]
 | Adresse=Lise-Meitner-Straße 15
 | Ort=89081 Ulm
 | OSM-Link=https://www.openstreetmap.org/?mlat=48.42375&mlon=9.93928#map=18
 | Homepage=https://www.akkodis.com/
}}
Akkodis ist ein Engineering-Dienstleister. [https://www.akkodis.com/de/ueber-uns Mehr]
"""

WIKI_CONTENT_NO_TEMPLATE = """Firma ohne Template.
https://www.openstreetmap.org/?mlat=1&mlon=2
Offizielle Seite: https://www.beispiel-firma.de/karriere
"""


def test_wiki_website_from_template():
    assert seed.wiki_website(WIKI_CONTENT) == "https://www.akkodis.com/"


def test_wiki_website_fallback_first_non_osm_url():
    assert seed.wiki_website(WIKI_CONTENT_NO_TEMPLATE) == "https://www.beispiel-firma.de/karriere"


def test_member_website_skips_footer_noise():
    html = ('<a href="https://startup-region-ulm.de/x">intern</a>'
            '<a href="https://www.ihk.de/ulm/impressum">IHK</a>'
            '<a href="https://tensor-solutions.com/">Firma</a>'
            '<a href="https://www.subreality.de">Footer-Designer</a>')
    assert seed.member_website(html) == "https://tensor-solutions.com/"


def test_member_name_from_h1():
    html = ("<title>Startup-Region Ulm</title>"
            '<h1 class="entry-title">Tensor AI Solutions GmbH</h1>')
    assert seed.member_name(html) == "Tensor AI Solutions GmbH"


def test_member_name_none_without_h1():
    assert seed.member_name("<title>Startup-Region Ulm</title>") is None


def test_member_website_none_if_only_noise():
    html = '<a href="https://www.ihk.de/x">IHK</a>'
    assert seed.member_website(html) is None


def make_row(name, website="", source="startup-region"):
    return {"company_id": seed.slugify(name), "name": name, "location_city": "Ulm",
            "location_region": "Ulm", "commute_minutes": "0", "website": website,
            "careers_url": "", "ats_type": "", "ats_slug": "", "ats_feed_url": "",
            "size_bucket": "", "industry": "", "tech_relevance": "1",
            "source": source, "source_url": "", "contact_email": "",
            "last_verified": "", "scrape_status": "", "notes": "",
            "active_werkstudent_seen": ""}


def test_merge_fills_empty_website_and_keeps_existing():
    rows = [make_row("Tensor Solutions GmbH"),
            make_row("BITE GmbH", website="https://www.b-ite.de/")]
    updates = [{"name": "Tensor Solutions", "website": "https://tensor-solutions.com/"},
               {"name": "BITE", "website": "https://FALSCH.example"}]
    stats = seed.merge_updates(rows, updates, source="test")
    assert rows[0]["website"] == "https://tensor-solutions.com/"
    assert rows[1]["website"] == "https://www.b-ite.de/"    # nicht überschreiben
    assert stats["filled"] == 1 and stats["added"] == 0


def test_merge_adds_unknown_company():
    rows = [make_row("Acme GmbH")]
    updates = [{"name": "Neue Firma UG", "website": "https://neue-firma.de"}]
    stats = seed.merge_updates(rows, updates, source="wiki")
    assert stats["added"] == 1
    added = rows[-1]
    assert added["name"] == "Neue Firma UG"
    assert added["website"] == "https://neue-firma.de"
    assert added["source"] == "wiki"


def test_slugify():
    assert seed.slugify("Jäger & Söhne GmbH") == "jaeger-soehne-gmbh"
