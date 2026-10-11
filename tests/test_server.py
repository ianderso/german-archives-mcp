"""The tools, called as a client calls them, against recorded answers."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx

from german_archives_mcp.client import DDB_HOST, LABW_HOST

from .conftest import (
    L10_510,
    OBERKASSEL_1811,
    OBERKASSEL_SERIES,
    call_tool,
    fixture,
    route_ddb,
    route_labw,
)


def _params(route) -> dict:
    return parse_qs(urlsplit(str(route.calls.last.request.url)).query)


# --------------------------------------------------------------------------- #
# ddb_search
# --------------------------------------------------------------------------- #
async def test_a_search_names_holder_signature_and_dates(served, sites):
    route = route_ddb(sites)
    out = await call_tool(
        "ddb_search",
        query="Geburtsregister",
        archive="Stadtarchiv Düsseldorf",
        has_images=True,
        year_to=1812,
        rows=3,
    )
    assert out["total"] == 19 and out["returned"] == 3 and out["next_page"] == 2
    first = out["hits"][0]
    assert first["institution"] == "Stadtarchiv Düsseldorf"
    assert first["signature"].startswith("7-0-7 Standesamtsregister")
    assert first["dates"] == "1811-1816"
    assert "finding aids written by the holding archive" in out["note"]
    params = _params(route)
    assert r"provider_fct:Stadtarchiv\ Düsseldorf*" in params["fq"]
    assert "digitalisat:true" in params["fq"]
    assert any(f.startswith("begin_time:[* TO ") for f in params["fq"])
    assert params["rows"] == ["3"]


async def test_a_sector_filters_by_the_ddbs_code(served, sites):
    route = route_ddb(sites)
    await call_tool("ddb_search", query="Geburtsregister", sector="archive")
    assert "sector_fct:sec_01" in _params(route)["fq"]


async def test_nothing_found_says_what_a_zero_covers(served, sites):
    route_ddb(sites)
    out = await call_tool("ddb_search", query="Zyxwvutsrq Qwertzuiopp")
    assert out["total"] == 0 and out["hits"] == []
    assert "not a negative" in out["note"]


async def test_a_search_needs_words_or_an_archive(served, sites):
    out = await call_tool("ddb_search")
    assert out["error"] == "no_criteria"


async def test_years_out_of_order_are_refused(served, sites):
    out = await call_tool("ddb_search", query="x", year_from=1900, year_to=1800)
    assert out["error"] == "invalid_argument"


async def test_paging_stops_where_a_search_needs_narrowing(served, sites):
    out = await call_tool("ddb_search", query="x", page=1000, rows=50)
    assert out["error"] == "paging_limit"


async def test_rows_are_capped(served, sites):
    route = route_ddb(sites)
    await call_tool("ddb_search", query="Geburtsregister", rows=5000)
    assert _params(route)["rows"] == ["50"]


async def test_a_landesarchiv_hit_carries_its_permalink(served, sites):
    route_ddb(sites, **{"Standesbuch": "ddb_signature_l10_510.json"})
    out = await call_tool("ddb_search", query="Standesbuch")
    assert out["hits"][0]["labw_permalink"] == "https://www.landesarchiv-bw.de/plink/?f=5-475861"


async def test_a_ddb_outage_is_not_an_empty_result(served, sites):
    sites.route(host=DDB_HOST).mock(return_value=httpx.Response(503, text="down"))
    out = await call_tool("ddb_search", query="x")
    assert out["error"] == "upstream_error" and "not an empty result" in out["message"]


async def test_an_unauthorised_answer_says_a_key_may_now_be_needed(served, sites):
    sites.route(host=DDB_HOST).mock(
        return_value=httpx.Response(403, json={"name": "NotAuthorizedException"})
    )
    out = await call_tool("ddb_search", query="x")
    assert out["error"] == "key_required"


# --------------------------------------------------------------------------- #
# ddb_item
# --------------------------------------------------------------------------- #
async def test_an_entry_is_read_with_its_place_in_the_fonds(served, sites):
    route_ddb(sites)
    out = await call_tool("ddb_item", id=OBERKASSEL_1811)
    assert out["signature"].endswith("7-0-7- 9.0003")
    assert out["institution"]["name"] == "Stadtarchiv Düsseldorf"
    assert out["hierarchy"][0]["title"] == "Stadtarchiv Düsseldorf"
    assert out["hierarchy"][-1]["title"] == "7-0-7-9.0000 Standesamt Oberkassel"
    assert out["images"]["count"] == 12
    assert out["citation"]["institution"] == "Stadtarchiv Düsseldorf"
    assert out["citation"]["signature"] == out["signature"]
    assert out["archivportal_url"].endswith(OBERKASSEL_1811)
    assert "children" not in out
    # Extracted fields are not repeated.
    assert "Archivaliensignatur" not in out["fields"]


async def test_a_landesarchiv_entry_points_at_labw_image(served, sites):
    route_ddb(sites)
    out = await call_tool("ddb_item", id=f"https://www.archivportal-d.de/item/{L10_510}")
    assert out["labw_permalink"] == "https://www.landesarchiv-bw.de/plink/?f=5-475861"
    assert out["holder_page"] == "https://www.landesarchiv-bw.de/plink/?f=5-475861"
    assert out["citation"]["url"] == out["holder_page"]
    assert out["rights"]["metadata"] == "http://creativecommons.org/publicdomain/zero/1.0/"
    assert any("labw_image" in n for n in out["notes"])


async def test_a_series_heading_lists_its_children(served, sites):
    route_ddb(sites)
    out = await call_tool("ddb_item", id=OBERKASSEL_SERIES, children=3)
    assert out["grouping_node"] is True
    assert out["title"] == "7-0-7-9.0000 Standesamt Oberkassel"
    assert out["children"]["total"] == 55 and out["children"]["next_offset"] == 3
    assert len(out["children"]["items"]) == 3


async def test_an_unknown_entry_is_not_found(served, sites):
    route_ddb(sites)
    out = await call_tool("ddb_item", id="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    assert out["error"] == "not_found"


async def test_a_malformed_id_is_refused_before_any_request(served, sites):
    out = await call_tool("ddb_item", id="../../etc/passwd")
    assert out["error"] == "invalid_id"


async def test_an_entry_survives_its_hierarchy_failing(served, sites):
    route_ddb(sites, **{f"{OBERKASSEL_1811}/parents": httpx.Response(500, text="x")})
    out = await call_tool("ddb_item", id=OBERKASSEL_1811)
    assert out["title"] and "hierarchy" not in out
    assert any("fonds context could not be read" in n for n in out["notes"])


# --------------------------------------------------------------------------- #
# labw_standesbuch
# --------------------------------------------------------------------------- #
async def test_the_books_for_a_place_and_year(served, sites):
    route_ddb(sites)
    route_labw(sites)
    out = await call_tool("labw_standesbuch", place="Breisach", year=1850)
    assert out["found"] == 4
    books = out["books"]
    assert [b["signature"] for b in books] == [
        "L 10 Nr. 469",
        "L 10 Nr. 481",
        "L 10 Nr. 510",
        "L 10 Nr. 517",
    ]
    assert books[0]["place_named_first"] is True
    assert books[0]["confessions"] == ["catholic", "jewish"]
    assert [b["image_count"] for b in books] == [391, 359, 380, 359]
    assert books[2]["permalink"] == "https://www.landesarchiv-bw.de/plink/?f=5-475861"
    assert "_scope" not in books[0]


async def test_the_search_asks_for_the_place_in_the_title_of_the_two_fonds(served, sites):
    route = route_ddb(sites)
    await call_tool("labw_standesbuch", place="Breisach", year=1850, count_images=False)
    params = _params(route)
    assert params["q"] == ['title:"Breisach"']
    assert any("Staatsarchiv Freiburg, L 10" in f and "Karlsruhe, 390" in f for f in params["fq"])


async def test_a_confession_keeps_its_books(served, sites):
    route_ddb(sites)
    out = await call_tool(
        "labw_standesbuch", place="Breisach", year=1850, confession="jewish", count_images=False
    )
    assert [b["signature"] for b in out["books"]] == ["L 10 Nr. 469"]


async def test_counting_images_can_be_left_out(served, sites):
    route_ddb(sites)
    labw = route_labw(sites)
    out = await call_tool("labw_standesbuch", place="Breisach", year=1850, count_images=False)
    assert labw.call_count == 0 and "image_count" not in out["books"][0]


async def test_a_place_outside_baden_finds_nothing_and_says_so(served, sites):
    route_ddb(sites)
    out = await call_tool("labw_standesbuch", place="Düsseldorf")
    assert out["books"] == [] and "not a negative" in out["notes"][0]


async def test_a_year_outside_the_standesbuecher_is_flagged(served, sites):
    route_ddb(sites)
    out = await call_tool("labw_standesbuch", place="Düsseldorf", year=1890)
    assert any("1810 to 1870" in n for n in out["notes"])


async def test_the_books_survive_the_landesarchiv_failing(served, sites):
    route_ddb(sites)
    sites.route(host=LABW_HOST).mock(return_value=httpx.Response(503, text="down"))
    out = await call_tool("labw_standesbuch", place="Breisach", year=1850)
    assert len(out["books"]) == 4
    assert out["books"][0]["image_count"] is None
    assert out["books"][0]["image_count_error"] == "upstream_error"
    assert any("still right" in n for n in out["notes"])


async def test_a_place_with_query_syntax_is_refused(served, sites):
    out = await call_tool("labw_standesbuch", place='x" OR title:*')
    assert out["error"] == "invalid_place"


# --------------------------------------------------------------------------- #
# labw_image
# --------------------------------------------------------------------------- #
async def test_a_page_is_saved_and_cited_by_signature(served, sites, tmp_path):
    route_ddb(sites)
    labw = route_labw(sites)
    target = tmp_path / "bild-378.jpg"
    out = await call_tool("labw_image", item="L 10 Nr. 510", page=378, destination=str(target))
    assert target.read_bytes() == fixture("labw_bild_243px.jpg")
    assert (out["width"], out["height"]) == (243, 182)
    assert out["page"] == 378 and out["pages"] == 380
    assert out["citation"]["text"] == (
        "Landesarchiv Baden-Württemberg, Abt. Staatsarchiv Freiburg, L 10 Nr. 510, Bild 378"
    )
    assert out["permalink"] == "https://www.landesarchiv-bw.de/plink/?f=5-475861-377"
    assert "Public Domain Mark" in out["rights"]
    bild = parse_qs(urlsplit(str(labw.calls.last.request.url)).query)
    assert bild["originalBilddatei"][0].endswith("05_0000475861_0378_5-475861-377.png")


async def test_a_permalink_to_an_image_finds_its_place_in_the_book(served, sites, tmp_path):
    route_labw(sites)
    out = await call_tool(
        "labw_image",
        item="https://www.landesarchiv-bw.de/plink/?f=5-475861-380",
        destination=str(tmp_path / "p.jpg"),
    )
    assert out["page"] == 119
    assert out["citation"]["image"] == "Bild 119"


async def test_a_permalink_and_a_page_that_disagree_are_refused(served, sites, tmp_path):
    route_labw(sites)
    out = await call_tool(
        "labw_image", item="5-475861-380", page=5, destination=str(tmp_path / "p.jpg")
    )
    assert out["error"] == "conflicting_page"


async def test_a_book_without_a_page_asks_for_one(served, sites, tmp_path):
    route_labw(sites)
    out = await call_tool("labw_image", item="5-475861", destination=str(tmp_path / "p.jpg"))
    assert out["error"] == "no_page" and out["pages"] == 380


async def test_a_page_past_the_end_is_refused(served, sites, tmp_path):
    route_labw(sites)
    out = await call_tool(
        "labw_image", item="5-475861", page=381, destination=str(tmp_path / "p.jpg")
    )
    assert out["error"] == "no_such_page" and not (tmp_path / "p.jpg").exists()


async def test_max_pixels_asks_again_at_a_smaller_zoom(served, sites, tmp_path):
    labw = route_labw(sites)
    out = await call_tool(
        "labw_image",
        item="5-475861",
        page=2,
        max_pixels=150,
        destination=str(tmp_path / "p.jpg"),
    )
    zooms = [
        parse_qs(urlsplit(str(c.request.url)).query)["zoom"][0]
        for c in labw.calls
        if c.request.url.path.endswith("bild.php")
    ]
    assert zooms[-2:] == ["100", "61"]
    assert out["width"] == 182


async def test_an_unknown_signature_points_to_the_permalink(served, sites, tmp_path):
    out = await call_tool(
        "labw_image", item="A 1 Nr. 2", page=1, destination=str(tmp_path / "p.jpg")
    )
    assert out["error"] == "unknown_signature" and "permalink" in out["message"]


async def test_a_signature_the_finding_aid_lacks_is_not_found(served, sites, tmp_path):
    route_ddb(sites)
    out = await call_tool(
        "labw_image", item="L 10 Nr. 99999", page=1, destination=str(tmp_path / "p.jpg")
    )
    assert out["error"] == "not_found"


async def test_a_permalink_to_nothing_is_not_found(served, sites, tmp_path):
    route_labw(sites)
    out = await call_tool("labw_image", item="5-1", page=1, destination=str(tmp_path / "p.jpg"))
    assert out["error"] == "not_found"


async def test_a_book_and_its_image_list_are_fetched_once(served, sites, tmp_path):
    route_ddb(sites)
    labw = route_labw(sites)
    for n in (1, 2):
        await call_tool(
            "labw_image", item="L 10 Nr. 510", page=n, destination=str(tmp_path / f"{n}.jpg")
        )
    names = [c.request.url.path.rsplit("/", 1)[-1] for c in labw.calls]
    assert names == ["plink.php", "thumbnails.php", "bild.php", "bild.php"]


async def test_a_landesarchiv_outage_is_not_an_empty_result(served, sites, tmp_path):
    sites.route(host=LABW_HOST).mock(side_effect=httpx.ConnectError("reset"))
    out = await call_tool(
        "labw_image", item="5-475861", page=1, destination=str(tmp_path / "p.jpg")
    )
    assert out["error"] == "upstream_error" and "Landesarchiv" in out["message"]


async def test_a_bot_check_is_reported_as_blocked(served, sites, tmp_path):
    sites.route(host=LABW_HOST).mock(
        return_value=httpx.Response(200, text="<html><title>Making sure you're not a bot!</title>")
    )
    out = await call_tool(
        "labw_image", item="5-475861", page=1, destination=str(tmp_path / "p.jpg")
    )
    assert out["error"] == "blocked" and "browser" in out["message"]


# --------------------------------------------------------------------------- #
# cache_status
# --------------------------------------------------------------------------- #
async def test_cache_status_reports_calls_and_pacing(served, sites):
    route_ddb(sites)
    await call_tool("ddb_search", query="Geburtsregister")
    await call_tool("ddb_search", query="Geburtsregister")
    out = await call_tool("cache_status")
    assert out["live_calls_this_session"] == 1 and out["cache_hits_this_session"] == 1
    assert out["calls_by_host"] == {DDB_HOST: 1}
    assert set(out["hosts"]) == {DDB_HOST, LABW_HOST}
