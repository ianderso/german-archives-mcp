"""Reading the Archive in NRW portal's hits and the Landesarchiv NRW's METS files."""

from __future__ import annotations

from urllib.parse import parse_qs, quote, urlsplit

import pytest

from german_archives_mcp import nrw

from .conftest import BARMEN_METS, LEMGO_METS, fixture


def test_the_search_address_carries_every_filter():
    url = nrw.search_url(
        keyword="Geburtsregister Barmen",
        archive="rheinland",
        year_from=1850,
        year_to=1851,
        page=2,
        size=10,
    )
    parts = urlsplit(url)
    params = parse_qs(parts.query)
    assert parts.hostname == "www.archive.nrw.de" and parts.path == "/sufservice/api/search"
    assert params == {
        "keyword": ["Geburtsregister Barmen"],
        "hasDigitalisat": ["true"],
        "archive": ["185"],
        "laufzeitVon": ["1850"],
        "laufzeitBis": ["1851"],
        "size": ["10"],
        "page": ["2"],
    }


def test_without_filters_the_search_leaves_them_out():
    params = parse_qs(urlsplit(nrw.search_url(keyword="x", has_images=False)).query)
    assert set(params) == {"keyword", "size", "page"}


def test_search_words_are_one_line_of_printable_text():
    assert nrw.clean_query("  Geburtsregister\n\tBarmen\x00 ") == "Geburtsregister Barmen"


def test_a_hit_names_archive_signature_dates_and_its_mets():
    doc = fixture("nrw_search_barmen_1850.json")["searchResult"][0]
    hit = nrw.hit(doc)
    assert hit["title"] == "Geburtsregister Barmen"
    assert hit["signature"] == "PA 2104 Nr. 69 - Band: 1"
    assert hit["fonds"] == "PA 2104 Zivilstandsregister Landgerichtsbezirk Elberfeld"
    assert hit["institution"] == "Landesarchiv NRW Abteilung Rheinland"
    assert hit["mets"] == BARMEN_METS and hit["readable_by_nrw_image"] is True
    assert hit["viewer"].startswith("https://dfg-viewer.de/show/")
    assert hit["level"] == "Verzeichnungseinheit"


def test_a_westphalian_hit_has_its_own_signature_form():
    doc = fixture("nrw_search_lemgo_1880.json")["searchResult"][0]
    hit = nrw.hit(doc)
    assert hit["signature"] == "P 3 / 9 Nr. 260"
    assert hit["title"] == "Sterberegister Standesamt Almena"
    assert hit["mets"] == LEMGO_METS


@pytest.mark.parametrize(
    "text,expected",
    [
        (BARMEN_METS, BARMEN_METS),
        (BARMEN_METS.replace("https://", "http://"), BARMEN_METS),
        ("https://dfg-viewer.de/show/?tx_dlf[id]=" + quote(LEMGO_METS, safe=""), LEMGO_METS),
        ("Abt_Ostwestfalen-Lippe/P3/P3-09/~002/P3-09_00260", LEMGO_METS),
        ("/Abt_Ostwestfalen-Lippe/P3/P3-09/~002/P3-09_00260/mets.xml", LEMGO_METS),
    ],
)
def test_an_item_is_read_in_every_form(text, expected):
    assert nrw.parse_item(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "https://www.duesseldorf.de/stadtarchiv/archivenrw/7/0/7/7_0_7_9_0001/mets.xml",
        "https://www.landesarchiv-nrw.de/digitalisate/../secret/mets.xml",
        "https://www.landesarchiv-nrw.de/digitalisate/Abt_Rheinland/x/mets.xml?a=b",
        "https://www.landesarchiv-nrw.de/dwl?f=Abt_Rheinland/PA_2104",
        "https://evil.example/digitalisate/Abt_Rheinland/PA_2104/mets.xml",
        "Abt_Rheinland/../../etc",
        "PA 2104 Nr. 69",
    ],
)
def test_anything_else_is_not_an_item(text):
    assert nrw.parse_item(text) is None


def test_only_jpegs_on_the_image_server_are_readable_images():
    good = "https://www.landesarchiv-nrw.de/data02/Abt_Rheinland/PA_2104/~000/x_0001.jpg"
    assert nrw.readable_image(good)
    for bad in (
        good.replace("https://", "http://"),
        good.replace("www.landesarchiv-nrw.de", "attacker.example"),
        good + "?x=1",
        "https://www.landesarchiv-nrw.de/data02/../etc/passwd.jpg",
        "https://www.landesarchiv-nrw.de/digitalisate/Abt_Rheinland/mets.xml",
    ):
        assert not nrw.readable_image(bad), bad


def test_a_mets_file_gives_title_pages_in_order_permalink_and_licence():
    mets = nrw.parse_mets(fixture("nrw_mets_p3-09_260.xml"))
    assert (
        mets.title
        == "Abteilung Ostwestfalen-Lippe, P 3 / 9 (Standesämter Landkreis Lemgo), Nr. 260"
    )
    assert len(mets.pages) == 14
    assert mets.pages[0].endswith("OWL_P3-09_00260_00001.jpg")
    assert mets.pages[13].endswith("OWL_P3-09_00260_00014.jpg")
    assert mets.permalink == (
        "https://www.archive.nrw.de/ms/search?link="
        "VERZEICHUNGSEINHEIT-Vz_4f087f7d-4aba-4b88-8558-434bd11d9c87"
    )
    assert mets.urn.startswith("urn:nbn:de:danrw:de2191-")
    assert "by-sa" in mets.license_url
    assert mets.signature == "P 3 / 9 Nr. 260"
    assert mets.archive == "Landesarchiv NRW Abteilung Ostwestfalen-Lippe"


def test_pages_follow_the_structure_map_not_the_file_list():
    text = fixture("nrw_mets_p3-09_260.xml")
    swapped = text.replace('ORDER="1" TYPE="page"', 'ORDER="99" TYPE="page"')
    mets = nrw.parse_mets(swapped)
    assert mets.pages[-1].endswith("_00001.jpg") and mets.pages[0].endswith("_00002.jpg")


def test_something_that_is_not_a_mets_file_is_not_read():
    assert nrw.parse_mets("<html><title>404 Not Found</title></html>") is None
    assert nrw.parse_mets('<mets:mets xmlns:mets="x"></mets:mets>') is None


def test_the_citation_names_archive_signature_image_and_permalink():
    mets = nrw.parse_mets(fixture("nrw_mets_pa2104_69bd1.xml"))
    cite = nrw.citation(mets, 7, BARMEN_METS)
    assert cite["text"] == "Landesarchiv NRW Abteilung Rheinland, PA 2104 Nr. 69 1, Bild 7"
    assert cite["fonds"] == "PA 2104 Zivilstandsregister Landgerichtsbezirk Elberfeld"
    assert cite["permalink"].endswith("Vz_05B2B3A3-B59E-4267-A806-968A3F98FC4D")


def test_the_departments_are_numbered_as_the_portal_numbers_them():
    assert {k: v[0] for k, v in nrw.ARCHIVES.items()} == {
        "rheinland": "185",
        "westfalen": "1",
        "ostwestfalen-lippe": "10003",
    }
