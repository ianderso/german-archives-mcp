"""APERTUS (Rheinland-Pfalz): reading its answers, and rlp_search and rlp_image end to end."""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest

from german_archives_mcp import rlp, server
from german_archives_mcp.client import APERTUS_HOST

from .conftest import ST_JOHANN_1817, call_tool, fixture, route_apertus

PDF_PATH = "/Bild/PStA_657,349_4.pdf"


def _page(name: str) -> str:
    return fixture(name).decode("latin-1")


# --------------------------------------------------------------------------- #
# Reading APERTUS's answers
# --------------------------------------------------------------------------- #
def test_a_query_is_built_as_the_sites_own_form_builds_it():
    assert rlp.query("Cochem", "death") == "Sterberegister+AND+Cochem"
    assert rlp.query("St. Johann (bei Mayen)") == "St.+AND+Johann+AND+bei+AND+Mayen"
    assert rlp.query("Münstermaifeld", "birth") == "Geburtsregister+AND+Münstermaifeld"


def test_the_search_form_carries_the_years_and_the_page():
    form = rlp.search_form(
        "Sterberegister+AND+Cochem", year_from=1880, year_to=None, start=25, rows=25
    )
    assert form["query"] == "Sterberegister+AND+Cochem"
    assert (form["range"], form["range2"]) == ("1880", "")
    assert (form["start"], form["rows"], form["doc"], form["archiv"]) == (
        "25",
        "25",
        "TRUE",
        "PStA",
    )
    assert form["bestand"] == "" and form["nummer"] == ""


def test_a_signature_look_up_names_the_fonds_and_number():
    form = rlp.signature_form("657,349", 4)
    assert (form["bestand"], form["nummer"], form["query"]) == ("657,349", "4", "")


def test_units_carry_signature_title_years_and_permalink():
    total, units = rlp.parse_units(_page("rlp_search_cochem_deaths_1880.html"))
    assert total == 4 and len(units) == 4
    first = units[0]
    assert first["signature"] == "Best. 657,377 Nr. 141"
    assert first["fonds"] == "657,377" and first["number"] == "141"
    assert first["title"] == "Sterberegister der Bürgermeisterei Cochem-Land"
    assert first["register"] == "death" and first["office"] == "Bürgermeisterei Cochem-Land"
    assert first["years"] == "1880" and first["dates"] == "01.01.1880 - 31.12.1880"
    assert first["archive"] == "Personenstandsarchiv Rheinland-Pfalz"
    assert first["permalink"] == rlp.permalink(first["guid"])
    assert {u["fonds"] for u in units} == {"657,377", "657,380"}


def test_an_umlaut_survives_the_sites_iso_8859_1():
    total, units = rlp.parse_units(_page("rlp_search_muenstermaifeld_1850.html"))
    assert total == 1
    assert units[0]["title"] == "Geburtsregister der Bürgermeisterei Münstermaifeld"


def test_a_bare_line_break_is_apertus_empty_answer():
    assert rlp.parse_units(_page("rlp_search_empty.html")) == (0, [])


def test_an_answer_of_another_shape_is_not_read_as_empty():
    assert rlp.parse_units("<html><body>Wartungsarbeiten</body></html>") is None


def test_a_unit_description_names_its_pdf_and_notes():
    unit = rlp.parse_unit(_page("rlp_unit_657-349_4.html"), ST_JOHANN_1817)
    assert unit.signature == "Best. 657,349 Nr. 4"
    assert unit.title == "Geburtsregister der Bürgermeisterei St. Johann (bei Mayen)"
    assert unit.years == "1817" and unit.dates == "01.01.1817 - 31.12.1817"
    assert unit.fonds_title == "Bürgermeisterei St. Johann (bei Mayen)"
    assert unit.pdf_path == PDF_PATH
    assert rlp.pdf_url(unit) == f"https://{APERTUS_HOST}{PDF_PATH}"
    assert unit.details == {"Enthält-Vermerk": "Enthält u.a.: Namensverzeichnis"}
    assert rlp.Unit.from_dict(unit.as_dict()) == unit


@pytest.mark.parametrize(
    "path",
    [
        "/Bild/../index.php",
        "https://elsewhere.example/x.pdf",
        "/Bild/PStA_657,349_4.pdf?x=1",
        "//elsewhere.example/Bild/x.pdf",
        "/admin/PStA.pdf",
    ],
)
def test_a_pdf_path_of_another_shape_is_never_kept(path):
    text = _page("rlp_unit_657-349_4.html").replace(PDF_PATH, path)
    assert rlp.parse_unit(text, ST_JOHANN_1817).pdf_path == ""


@pytest.mark.parametrize(
    "text",
    [
        "Best. 657,349 Nr. 4",
        "657,349 Nr. 4",
        "Bestand 657,349 Nummer 4",
        "LHA Ko Best. 657,349 Nr. 4",
        "  Best.  657,349   Nr.  4 ",
    ],
)
def test_signatures_are_read_in_the_forms_people_write(text):
    assert rlp.parse_item(text) == ("signature", ("657,349", 4))


def test_a_guid_is_read_bare_or_from_the_permalink():
    link = f"https://{APERTUS_HOST}/index.php?PLINK=1&ID={ST_JOHANN_1817.upper()}"
    assert rlp.parse_item(link) == ("guid", ST_JOHANN_1817)
    assert rlp.parse_item(ST_JOHANN_1817) == ("guid", ST_JOHANN_1817)


@pytest.mark.parametrize(
    "text",
    ["", "Cochem", "https://elsewhere.example/index.php?ID=" + ST_JOHANN_1817, "657 Nr. 4"],
)
def test_anything_else_is_not_an_item(text):
    assert rlp.parse_item(text) is None


def test_the_citation_names_holder_signature_page_and_permalink():
    unit = rlp.parse_unit(_page("rlp_unit_657-349_4.html"), ST_JOHANN_1817)
    cite = rlp.citation(unit, 3)
    assert cite["text"].startswith(
        "Landesarchivverwaltung Rheinland-Pfalz, Landeshauptarchiv Koblenz, Best. 657,349 Nr. 4"
    )
    assert cite["text"].endswith("PDF page 3")
    assert cite["short"] == "LHA Ko Best. 657,349 Nr. 4"
    assert cite["permalink"] == f"https://{APERTUS_HOST}/index.php?PLINK=1&ID={ST_JOHANN_1817}"


# --------------------------------------------------------------------------- #
# rlp_search
# --------------------------------------------------------------------------- #
async def test_rlp_search_lists_units_with_an_item_for_rlp_image(served, sites):
    route = route_apertus(sites)
    out = await call_tool("rlp_search", place="Cochem", register="death", year_from=1880)
    assert out["total"] == 4 and out["returned"] == 4 and out["next_page"] is None
    assert out["query"] == "Sterberegister Cochem"
    assert out["units"][0]["item"] and "guid" not in out["units"][0]
    assert "signature" in out["note"] and "whole volume" in out["note"]
    sent = route.calls.last.request
    assert sent.method == "POST" and sent.url.path == "/queryOneExt.php"
    form = dict(httpx.QueryParams(sent.content.decode()))
    assert form["query"] == "Sterberegister+AND+Cochem" and form["range"] == "1880"


async def test_rlp_search_is_cached_for_a_day(served, sites):
    route = route_apertus(sites)
    await call_tool("rlp_search", place="Cochem", register="death")
    await call_tool("rlp_search", place="Cochem", register="death")
    assert route.call_count == 1


async def test_rlp_search_that_finds_nothing_says_what_a_zero_covers(served, sites):
    route_apertus(sites)
    out = await call_tool("rlp_search", place="Zyxwvutsrq")
    assert out["total"] == 0 and out["units"] == []
    assert "not a negative" in out["note"] and "Bürgermeisterei" in out["note"]


async def test_rlp_search_refuses_a_place_that_is_not_one(served, sites):
    out = await call_tool("rlp_search", place="x:*")
    assert out["error"] == "invalid_place"
    out = await call_tool("rlp_search", place="Cochem", year_from=1890, year_to=1880)
    assert out["error"] == "invalid_argument"


async def test_rlp_search_reports_a_changed_answer_as_such(served, sites):
    route_apertus(sites, **{"Sterberegister+AND+Cochem": b"<html><body>neu</body></html>"})
    out = await call_tool("rlp_search", place="Cochem", register="death")
    assert out["error"] == "api_changed"


# --------------------------------------------------------------------------- #
# rlp_image
# --------------------------------------------------------------------------- #
async def test_rlp_image_downloads_the_volume_once_and_reads_pages_from_disk(
    served, sites, tmp_path
):
    route = route_apertus(sites)
    first = await call_tool(
        "rlp_image", item="Best. 657,349 Nr. 4", page=2, destination=str(tmp_path / "p2.jpg")
    )
    assert first["format"] == "jpeg" and first["pages"] == 3 and first["page"] == 2
    assert (tmp_path / "p2.jpg").read_bytes()[:3] == b"\xff\xd8\xff"
    assert (first["width"], first["height"]) == (250, 366)
    assert first["signature"] == "Best. 657,349 Nr. 4" and first["years"] == "1817"
    assert first["volume"]["from_disk"] is False
    assert first["citation"]["page"] == "PDF page 2"
    assert "free download" in first["rights"]
    assert first["archive_notes"] == {"Enthält-Vermerk": "Enthält u.a.: Namensverzeichnis"}
    calls = [(c.request.method, c.request.url.path) for c in route.calls]
    assert calls == [("POST", "/queryOneExt.php"), ("POST", "/vz_php.php"), ("GET", PDF_PATH)]

    second = await call_tool(
        "rlp_image", item=ST_JOHANN_1817, page=3, destination=str(tmp_path / "p3.jpg")
    )
    assert second["volume"]["from_disk"] is True and second["page"] == 3
    assert route.call_count == 3, "the second page must not ask APERTUS for anything"


async def test_rlp_image_by_signature_again_costs_no_request(served, sites, tmp_path):
    route = route_apertus(sites)
    for n in (1, 2):
        out = await call_tool(
            "rlp_image", item="Best. 657,349 Nr. 4", page=n, destination=str(tmp_path / f"{n}.jpg")
        )
        assert out["page"] == n
    assert route.call_count == 3


async def test_two_pages_asked_at_once_share_one_download(served, sites, tmp_path):
    import asyncio

    route = route_apertus(sites)
    results = await asyncio.gather(
        *(
            call_tool(
                "rlp_image", item=ST_JOHANN_1817, page=n, destination=str(tmp_path / f"{n}.jpg")
            )
            for n in (1, 2, 3)
        )
    )
    assert [r["page"] for r in results] == [1, 2, 3]
    assert [c.request.url.path for c in route.calls].count(PDF_PATH) == 1


async def test_a_page_past_the_end_says_how_many_there_are(served, sites, tmp_path):
    route_apertus(sites)
    out = await call_tool(
        "rlp_image", item=ST_JOHANN_1817, page=9, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "no_such_page" and out["pages"] == 3
    assert not (tmp_path / "a.jpg").exists()


async def test_an_expired_volume_is_downloaded_again(served, sites, tmp_path, monkeypatch):
    route = route_apertus(sites)
    await call_tool("rlp_image", item=ST_JOHANN_1817, page=1, destination=str(tmp_path / "a.jpg"))
    meta = server.runtime.volumes_().root / f"{ST_JOHANN_1817}.json"
    entry = json.loads(meta.read_text())
    entry["stored"] = time.time() - 4 * 86_400
    meta.write_text(json.dumps(entry))
    out = await call_tool(
        "rlp_image", item=ST_JOHANN_1817, page=1, destination=str(tmp_path / "b.jpg")
    )
    assert out["volume"]["from_disk"] is False
    assert [c.request.url.path for c in route.calls].count(PDF_PATH) == 2


async def test_an_unknown_signature_is_not_found_without_opening_anything(served, sites, tmp_path):
    route = route_apertus(sites)
    out = await call_tool(
        "rlp_image", item="Best. 657,999 Nr. 1", page=1, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "not_found"
    assert [c.request.url.path for c in route.calls] == ["/queryOneExt.php"]


async def test_an_unknown_guid_is_not_found(served, sites, tmp_path):
    route_apertus(sites)
    guid = "00000000-0000-4000-8000-000000000000"
    out = await call_tool("rlp_image", item=guid, page=1, destination=str(tmp_path / "a.jpg"))
    assert out["error"] == "not_found"


async def test_a_unit_without_images_says_so(served, sites, tmp_path):
    text = fixture("rlp_unit_657-349_4.html").replace(
        b"<embed class='pdfimage' src='/Bild/PStA_657,349_4.pdf'></embed>", b""
    )
    route = route_apertus(sites, **{ST_JOHANN_1817: text})
    out = await call_tool(
        "rlp_image", item=ST_JOHANN_1817, page=1, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "no_images" and out["permalink"].endswith(ST_JOHANN_1817)
    assert PDF_PATH not in [c.request.url.path for c in route.calls]


async def test_a_pdf_that_vanished_is_an_outage_not_a_zero(served, sites, tmp_path):
    route_apertus(sites, **{PDF_PATH: httpx.Response(404, text="gone")})
    out = await call_tool(
        "rlp_image", item=ST_JOHANN_1817, page=1, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "upstream_error" and "not an empty result" in out["message"]
    root = server.runtime.volumes_().root
    assert not root.exists() or list(root.iterdir()) == []


async def test_something_that_is_not_a_pdf_is_not_kept(served, sites, tmp_path):
    route_apertus(sites, **{PDF_PATH: b"<html>Fehler</html>"})
    out = await call_tool(
        "rlp_image", item=ST_JOHANN_1817, page=1, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "not_a_pdf"
    root = server.runtime.volumes_().root
    assert not root.exists() or list(root.iterdir()) == []
    assert not (tmp_path / "a.jpg").exists()


async def test_a_volume_over_the_cap_is_refused_as_it_streams(served, sites, tmp_path, monkeypatch):
    big = httpx.Response(
        200, content=b"%PDF-1.4\n" + b"0" * 2_000, headers={"content-type": "application/pdf"}
    )
    route_apertus(sites, **{PDF_PATH: big})
    monkeypatch.setattr(server.runtime.config, "pdf_cache_mb", 0.001)
    out = await call_tool(
        "rlp_image", item=ST_JOHANN_1817, page=1, destination=str(tmp_path / "a.jpg")
    )
    assert out["error"] == "too_large" and "GERMAN_ARCHIVES_PDF_CACHE_MB" in out["message"]
    root = server.runtime.volumes_().root
    assert not root.exists() or list(root.iterdir()) == []


async def test_rlp_image_refuses_before_any_request(served, sites, tmp_path):
    route = route_apertus(sites)
    for item, page, dest, error in [
        ("Cochem", 1, tmp_path / "a.jpg", "unknown_item"),
        (ST_JOHANN_1817, 0, tmp_path / "b.jpg", "no_such_page"),
        (ST_JOHANN_1817, 1, tmp_path / "c.png", "bad_extension"),
        (ST_JOHANN_1817, 1, "relative.jpg", "relative_destination"),
    ]:
        out = await call_tool("rlp_image", item=item, page=page, destination=str(dest))
        assert out["error"] == error, out
    assert route.call_count == 0


async def test_rlp_image_never_overwrites(served, sites, tmp_path):
    route_apertus(sites)
    target = tmp_path / "exists.jpg"
    target.write_bytes(b"mine")
    out = await call_tool("rlp_image", item=ST_JOHANN_1817, page=1, destination=str(target))
    assert out["error"] == "destination_exists" and target.read_bytes() == b"mine"


async def test_cache_status_reports_the_volumes_on_disk(served, sites, tmp_path):
    route_apertus(sites)
    await call_tool("rlp_image", item=ST_JOHANN_1817, page=1, destination=str(tmp_path / "a.jpg"))
    out = await call_tool("cache_status")
    assert out["volume_pdfs"]["volumes"] == 1 and out["volume_pdfs"]["cap_megabytes"] == 1000
    assert out["calls_by_host"] == {APERTUS_HOST: 2}
    assert os.path.isdir(out["volume_pdfs"]["folder"])
