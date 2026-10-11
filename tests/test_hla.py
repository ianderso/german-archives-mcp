"""Hesse: LAGIS's catalogue and Arcinsys's METS files, and hessen_search and hessen_image."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from german_archives_mcp import hla
from german_archives_mcp.client import ARCINSYS_HOST, HLA_IMAGE_HOST, LAGIS_HOST

from .conftest import KORBACH_1880, call_tool, fixture, route_hessen

KORBACH_PERMALINK = f"https://{ARCINSYS_HOST}/arcinsys/detailAction?detailid=v{KORBACH_1880}"


# --------------------------------------------------------------------------- #
# Reading LAGIS and Arcinsys
# --------------------------------------------------------------------------- #
def test_search_words_are_the_place_the_register_and_the_year():
    assert hla.search_terms("Korbach", "birth", 1880) == "Korbach Geburtsnebenregister 1880"
    assert hla.search_terms("Bad Wildungen (Stadt)") == "Bad Wildungen Stadt"


def test_the_search_address_is_lagis_simple_search():
    parts = urlsplit(hla.search_url("Korbach Geburtsnebenregister", page=2, rows=10))
    assert parts.hostname == LAGIS_HOST
    assert parts.path == "/de/api/gsearch/sn/hessische-geburten-ehe-sterberegister"
    assert parse_qs(parts.query) == {
        "suchbegriff": ["Korbach Geburtsnebenregister"],
        "seite": ["2"],
        "datensaetze": ["10"],
    }


def test_a_hit_names_standesamt_register_years_and_signature():
    doc = fixture("lagis_korbach_births_1880.json")["results"][0]
    hit = hla.hit(doc)
    assert hit == {
        "title": "Korbach, Geburtsnebenregister, 1880",
        "standesamt": "Korbach",
        "register": "birth",
        "years": "1880",
        "signature": "HStAM 922 Nr. 6013",
        "archive": "Hessisches Staatsarchiv Marburg",
        "lagis_id": "922-6013",
        "lagis_permalink": hla.LAGIS_PERMALINK.format(id="922-6013"),
    }


def test_an_older_title_form_is_read_too():
    hit = hla.hit(
        {
            "id": "900-6",
            "title": "Affolterbach, Geburtsnebenregister (1880)",
            "subTitle": "HStAM Best. 900 Nr. 6",
        }
    )
    assert (hit["standesamt"], hit["register"], hit["years"]) == ("Affolterbach", "birth", "1880")
    assert hit["signature"] == "HStAM 900 Nr. 6"


@pytest.mark.parametrize(
    "text",
    [
        "HStAM 922 Nr. 6013",
        "HStAM Bestand 922 Nr. 6013",
        "HStAM Best. 922 Nr. 6013",
        "hstam, 922, 6013",
    ],
)
def test_signatures_are_read_in_the_forms_people_write(text):
    assert hla.parse_item(text) == ("signature", ("HStAM", "922", 6013))


@pytest.mark.parametrize(
    "text",
    [
        KORBACH_PERMALINK,
        f"https://{ARCINSYS_HOST}/arcinsys/detailAction.action?detailid=v{KORBACH_1880}",
        f"https://{ARCINSYS_HOST}/arcinsys/digitalMediaViewer.action?"
        f"archivalDescriptionId={KORBACH_1880}&selectId=1",
        f"https://{ARCINSYS_HOST}/arcinsys/mets?detailid=v{KORBACH_1880}",
        f"v{KORBACH_1880}",
    ],
)
def test_an_arcinsys_address_names_the_unit(text):
    assert hla.parse_item(text) == ("id", KORBACH_1880)


@pytest.mark.parametrize(
    "text",
    ["", "Korbach", "XStAM 922 Nr. 1", f"https://elsewhere.example/x?detailid=v{KORBACH_1880}"],
)
def test_anything_else_is_not_an_item(text):
    assert hla.parse_item(text) is None


def test_only_an_exact_number_counts_in_the_autocompleters_answer():
    answer = {
        "stueckSignatureSuggestions": [
            {"selectKey": "641219", "selectValue": "100"},
            {"selectKey": "2884088", "selectValue": "10"},
        ]
    }
    assert hla.unit_id(answer, 10) == 2884088
    assert hla.unit_id(answer, 1) is None
    assert hla.unit_id(fixture("arcinsys_items_922_6013.json"), 6013) == KORBACH_1880


def test_a_mets_file_lists_pages_in_viewer_order():
    mets = hla.parse_mets(fixture("arcinsys_mets_922_6013.xml"))
    assert mets.title == "Standesamt Korbach Geburtsnebenregister 1880"
    assert mets.shelf == "HStAM 922 6013" and mets.signature == "HStAM 922 Nr. 6013"
    assert mets.owner == "Hessisches Staatsarchiv Marburg" and mets.license == ""
    assert len(mets.pages) == 12
    assert mets.pages[0] == f"https://{HLA_IMAGE_HOST}/hstam/922/6013/00001.jpg"
    assert all(hla.readable_image(p) for p in mets.pages)


def test_a_withheld_page_shifts_the_numbering():
    """Arcinsys leaves out pages under a protection period; page n is the nth shown."""
    text = fixture("arcinsys_mets_922_6013.xml")
    start = text.index('<ns2:div ID="div_v3797740_default_154654670"')
    end = text.index("</ns2:div>", start) + len("</ns2:div>")
    mets = hla.parse_mets(text[:start] + text[end:])
    assert len(mets.pages) == 11
    assert mets.pages[1].endswith("/00003.jpg")


def test_something_that_is_not_mets_is_not_read():
    assert hla.parse_mets("<html><title>Fehler</title></html>") is None


@pytest.mark.parametrize(
    "url",
    [
        f"https://{HLA_IMAGE_HOST}/hstam/922/6013/../../x.jpg",
        f"https://{HLA_IMAGE_HOST}/hstam/922/6013/00001.jpg?x=1",
        f"http://{HLA_IMAGE_HOST}/hstam/922/6013/00001.jpg",
        f"https://{ARCINSYS_HOST}/hstam/922/6013/00001.jpg",
        f"https://{HLA_IMAGE_HOST}/hstam/922/6013/00001.php",
    ],
)
def test_an_image_address_of_another_shape_is_not_read(url):
    assert hla.readable_image(url) is False


def test_the_citation_names_archive_signature_image_and_permalink():
    mets = hla.parse_mets(fixture("arcinsys_mets_922_6013.xml"))
    cite = hla.citation(mets, 2, KORBACH_1880, mets.pages[1])
    assert cite["text"] == (
        "Hessisches Staatsarchiv Marburg, HStAM 922 Nr. 6013 "
        "(Standesamt Korbach Geburtsnebenregister 1880), Bild 2"
    )
    assert cite["file"] == "00002.jpg" and cite["permalink"] == KORBACH_PERMALINK


# --------------------------------------------------------------------------- #
# hessen_search
# --------------------------------------------------------------------------- #
async def test_hessen_search_finds_a_register_by_place_type_and_year(served, sites):
    lagis, _, _ = route_hessen(sites)
    out = await call_tool("hessen_search", place="Korbach", register="birth", year=1880)
    assert out["total"] == 1 and out["hits"][0]["signature"] == "HStAM 922 Nr. 6013"
    assert out["query"] == "Korbach Geburtsnebenregister 1880"
    assert "hessen_image" in out["note"]
    assert lagis.calls.last.request.url.params["datensaetze"] == "25"


async def test_hessen_search_sorts_a_page_by_standesamt_register_and_year(served, sites):
    route_hessen(sites)
    out = await call_tool("hessen_search", place="Korbach", register="birth")
    assert out["total"] == 25 and out["returned"] == 25
    years = [h["years"] for h in out["hits"]]
    assert years == sorted(years) and years[0] == "1876"


async def test_hessen_search_that_finds_nothing_says_what_a_zero_covers(served, sites):
    route_hessen(sites)
    out = await call_tool("hessen_search", place="Zyxwvutsrq")
    assert out["total"] == 0 and out["hits"] == []
    assert "not a negative" in out["note"] and "Standesamt" in out["note"]


async def test_hessen_search_caps_a_page_at_lagis_limit(served, sites):
    lagis, _, _ = route_hessen(sites)
    await call_tool("hessen_search", place="Korbach", rows=50)
    assert lagis.calls.last.request.url.params["datensaetze"] == "25"


async def test_hessen_search_reports_a_changed_answer_as_such(served, sites):
    route_hessen(sites, **{"Korbach": {"unexpected": True}})
    out = await call_tool("hessen_search", place="Korbach")
    assert out["error"] == "api_changed"


# --------------------------------------------------------------------------- #
# hessen_image
# --------------------------------------------------------------------------- #
async def test_hessen_image_reads_a_page_by_signature(served, sites, tmp_path):
    _, arcinsys, images = route_hessen(sites)
    target = tmp_path / "922-6013-2.jpg"
    out = await call_tool(
        "hessen_image", item="HStAM 922 Nr. 6013", page=2, destination=str(target)
    )
    assert out["format"] == "jpeg" and (out["width"], out["height"]) == (109, 150)
    assert out["pages"] == 12 and out["signature"] == "HStAM 922 Nr. 6013"
    assert out["permalink"] == KORBACH_PERMALINK
    assert out["citation"]["image"] == "Bild 2" and out["citation"]["file"] == "00002.jpg"
    assert "no licence" in out["rights"]
    assert target.read_bytes()[:3] == b"\xff\xd8\xff"
    assert [c.request.url.path for c in arcinsys.calls] == [
        "/arcinsys/queryItemSignatureSuggestions",
        "/arcinsys/mets",
    ]
    assert [c.request.url.path for c in images.calls] == [
        "/hstam/922/6013/00002.jpg",
        "/hstam/922/6013/max/00002.jpg",
    ]


async def test_a_second_page_costs_only_its_image(served, sites, tmp_path):
    _, arcinsys, _ = route_hessen(sites)
    for n in (1, 2):
        await call_tool(
            "hessen_image",
            item="HStAM 922 Nr. 6013",
            page=n,
            destination=str(tmp_path / f"{n}.jpg"),
        )
    assert arcinsys.call_count == 2


async def test_hessen_image_reads_a_page_by_permalink(served, sites, tmp_path):
    _, arcinsys, _ = route_hessen(sites)
    out = await call_tool(
        "hessen_image", item=KORBACH_PERMALINK, page=1, destination=str(tmp_path / "a.jpg")
    )
    assert out["page"] == 1 and out["source_url"].endswith("/00001.jpg")
    assert [c.request.url.path for c in arcinsys.calls] == ["/arcinsys/mets"]


async def test_without_a_page_it_says_how_many_there_are(served, sites, tmp_path):
    _, _, images = route_hessen(sites)
    out = await call_tool(
        "hessen_image", item="HStAM 922 Nr. 6013", destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "no_page" and out["pages"] == 12
    out = await call_tool(
        "hessen_image", item="HStAM 922 Nr. 6013", page=13, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "no_such_page" and out["pages"] == 12
    assert images.call_count == 0 and not (tmp_path / "a.jpg").exists()


async def test_an_unknown_signature_is_not_found(served, sites, tmp_path):
    route_hessen(sites)
    out = await call_tool(
        "hessen_image", item="HStAM 922 Nr. 999999", page=1, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "not_found"


async def test_a_unit_arcinsys_will_not_show_is_not_found(served, sites, tmp_path):
    """Arcinsys redirects an unknown unit's METS request to its error page."""
    route_hessen(sites)
    out = await call_tool(
        "hessen_image", item="v999999999", page=1, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "not_found"


async def test_a_unit_with_no_images_says_so(served, sites, tmp_path):
    empty = re.sub(
        r"<ns2:file\b.*?</ns2:file>", "", fixture("arcinsys_mets_922_6013.xml"), flags=re.S
    )
    route_hessen(sites, **{f"v{KORBACH_1880}": empty})
    out = await call_tool(
        "hessen_image", item=f"v{KORBACH_1880}", page=1, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "no_images" and out["permalink"] == KORBACH_PERMALINK


async def test_an_image_that_is_not_one_is_not_saved(served, sites, tmp_path):
    route_hessen(sites, image=httpx.Response(200, text="<html>Fehler</html>"))
    target = tmp_path / "a.jpg"
    out = await call_tool("hessen_image", item=f"v{KORBACH_1880}", page=1, destination=str(target))
    assert out["error"] == "not_an_image" and not target.exists()


async def test_hessen_image_refuses_before_any_request(served, sites, tmp_path):
    lagis, arcinsys, images = route_hessen(sites)
    for item, dest, error in [
        ("Korbach", tmp_path / "a.jpg", "unknown_item"),
        ("HStAM 922 Nr. 6013", tmp_path / "a.png", "bad_extension"),
        ("HStAM 922 Nr. 6013", tmp_path / ".hidden" / "a.jpg", "hidden_path"),
    ]:
        out = await call_tool("hessen_image", item=item, page=1, destination=str(dest))
        assert out["error"] == error, out
    assert lagis.call_count == arcinsys.call_count == images.call_count == 0
