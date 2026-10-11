"""The tools, called as a client calls them, against recorded answers."""

from __future__ import annotations

from urllib.parse import parse_qs, quote, urlsplit

import httpx

from german_archives_mcp import labw
from german_archives_mcp.client import (
    ALLOWED_HOSTS,
    DDB_HOST,
    LABW_HOST,
    NRW_PORTAL_HOST,
)

from .conftest import (
    BARMEN_METS,
    L10_510,
    LEMGO_METS,
    OBERKASSEL_1811,
    OBERKASSEL_SERIES,
    call_tool,
    fixture,
    route_ddb,
    route_labw,
    route_nrw,
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
    out = await call_tool("labw_standesbuch", place="Breisach", year=1850, fonds="L 10")
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
    assert books[0]["fonds"] == "L 10" and books[0]["has_images"] is True
    assert [b["image_count"] for b in books] == [391, 359, 380, 359]
    assert books[2]["permalink"] == "https://www.landesarchiv-bw.de/plink/?f=5-475861"
    assert "_scope" not in books[0] and "_order" not in books[0]


async def test_every_fonds_is_searched_unless_one_is_named(served, sites):
    route = route_ddb(sites)
    out = await call_tool("labw_standesbuch", place="Breisach", year=1850, count_images=False)
    params = _params(route)
    assert params["q"] == [labw.books_query("Breisach")]
    fonds_filter = next(f for f in params["fq"] if f.startswith("apd_reference_number:"))
    for key in ("L 10", "390", "F 901", "Wü 110 T 1", "J 386", "Dep. 1 T 37", "Dep. 1 T 44"):
        assert key in fonds_filter
    assert labw.NO_HEADINGS in params["fq"]
    # The Jewish registers of Breisach come with its own Catholic book, ahead of
    # the villages filed under Breisach; within a fonds and place, by year.
    assert [b["signature"] for b in out["books"]] == [
        "L 10 Nr. 469",
        "J 386 Bü 107",
        "J 386 Bü 104",
        "J 386 Bü 105",
        "L 10 Nr. 481",
        "L 10 Nr. 510",
        "L 10 Nr. 517",
    ]
    jewish = out["books"][1]
    assert jewish["fonds"] == "J 386" and jewish["confessions"] == ["jewish"]
    assert jewish["archive"].endswith("Abt. Hauptstaatsarchiv Stuttgart")
    assert "district_court" not in jewish


async def test_naming_a_fonds_searches_only_that_one(served, sites):
    route = route_ddb(sites)
    await call_tool(
        "labw_standesbuch", place="Breisach", year=1850, fonds="L 10", count_images=False
    )
    params = _params(route)
    assert params["q"] == ['title:"Breisach"']
    assert 'apd_reference_number:("Staatsarchiv Freiburg, L 10")' in params["fq"]


async def test_wuerttemberg_books_are_found_by_their_parish_heading(served, sites):
    route_ddb(sites)
    out = await call_tool("labw_standesbuch", place="Ulm", year=1850, count_images=False)
    assert out["found"] == 49
    by_signature = {b["signature"]: b for b in out["books"]}
    protestant = by_signature["Wü 110 T 1 Nr. 4566"]
    assert protestant["title"] == "Taufregister XII mit Register"
    assert protestant["place"] == "Ulm, Münster (Ulm UL)"
    assert protestant["place_named_first"] is True
    assert protestant["confessions"] == ["protestant"]
    assert protestant["registers"][0] == "baptisms"
    assert protestant["archive"].endswith("Abt. Staatsarchiv Sigmaringen")
    catholic = by_signature["F 901 Bd 1511"]
    assert catholic["place"] == "Ulm (St. Michael zu den Wengen)"
    assert catholic["confessions"] == ["catholic"] and catholic["years"] == "1849-1867"
    village = by_signature["F 901 Bd 398"]
    assert village["place"] == "Einsingen, Ulm UL" and village["place_named_first"] is False
    # Baden has villages called Ulm too, each with its own book.
    assert by_signature["390 Nr. 923"]["place_named_first"] is True
    assert by_signature["390 Nr. 923"]["district_court"] == "Bühl"
    # Volumes the duplicates never included are listed, and said not to be online.
    missing = by_signature["Wü 110 T 1 {1754: nicht vorhanden}"]
    assert missing["has_images"] is False
    assert any("nicht vorhanden" in n for n in out["notes"])
    # The place's own books come first.
    firsts = [b["place_named_first"] for b in out["books"]]
    assert firsts == sorted(firsts, reverse=True)


async def test_a_confession_keeps_its_books(served, sites):
    route_ddb(sites)
    out = await call_tool(
        "labw_standesbuch", place="Breisach", year=1850, confession="jewish", count_images=False
    )
    assert [b["signature"] for b in out["books"]] == [
        "L 10 Nr. 469",
        "J 386 Bü 107",
        "J 386 Bü 104",
        "J 386 Bü 105",
    ]


async def test_a_fonds_confession_counts_for_every_book_in_it(served, sites):
    route_ddb(sites)
    out = await call_tool(
        "labw_standesbuch", place="Ulm", year=1850, confession="protestant", count_images=False
    )
    assert out["books"] and {b["fonds"] for b in out["books"]} == {"Wü 110 T 1"}


async def test_counting_images_can_be_left_out(served, sites):
    route_ddb(sites)
    labw_route = route_labw(sites)
    out = await call_tool("labw_standesbuch", place="Breisach", year=1850, count_images=False)
    assert labw_route.call_count == 0 and "image_count" not in out["books"][0]


async def test_only_books_with_images_are_counted(served, sites):
    route_ddb(sites)
    labw_route = route_labw(sites)
    out = await call_tool("labw_standesbuch", place="Ulm", year=1850)
    counted = [b for b in out["books"] if "image_count" in b]
    assert len(counted) == 4 and all(b["has_images"] for b in counted)
    assert labw_route.call_count <= 8


async def test_a_place_outside_baden_wuerttemberg_finds_nothing_and_says_so(served, sites):
    route_ddb(sites)
    out = await call_tool("labw_standesbuch", place="Düsseldorf")
    assert out["books"] == [] and "not a negative" in out["notes"][0]


async def test_a_year_outside_the_registers_is_flagged(served, sites):
    route_ddb(sites)
    out = await call_tool("labw_standesbuch", place="Düsseldorf", year=1890)
    assert any("1810 to 1870" in n and "1808 to 1875" in n for n in out["notes"])


async def test_the_books_survive_the_landesarchiv_failing(served, sites):
    route_ddb(sites)
    sites.route(host=LABW_HOST).mock(return_value=httpx.Response(503, text="down"))
    out = await call_tool("labw_standesbuch", place="Breisach", year=1850, fonds="L 10")
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


async def test_a_wuerttemberg_catholic_duplicate_is_read_by_signature(served, sites, tmp_path):
    route_ddb(sites)
    labw_route = route_labw(sites)
    out = await call_tool(
        "labw_image", item="StAL F 901 Bd. 1511", page=3, destination=str(tmp_path / "f.jpg")
    )
    assert out["signature"] == "F 901 Bd 1511" and out["pages"] == 290
    assert out["citation"]["text"] == (
        "Landesarchiv Baden-Württemberg, Abt. Staatsarchiv Ludwigsburg, F 901 Bd 1511, Bild 3"
    )
    assert out["permalink"] == "https://www.landesarchiv-bw.de/plink/?f=2-181572-3"
    assert "Public Domain Mark" in out["rights"]
    bild = parse_qs(urlsplit(str(labw_route.calls.last.request.url)).query)
    assert bild["scopeid_besta"] == ["3493"]
    assert bild["originalBilddatei"][0].startswith(
        "/data/bildcms/internetbilder/archiv_2/olf/bestand_0000003493/titlaufn_0000181572/"
    )


async def test_a_protestant_duplicate_is_read_by_permalink(served, sites, tmp_path):
    route_labw(sites)
    out = await call_tool(
        "labw_image",
        item="https://www.landesarchiv-bw.de/plink/?f=6-2785143",
        page=1,
        destination=str(tmp_path / "w.jpg"),
    )
    assert out["signature"] == "Wü 110 T 1 Nr. 4566"
    assert out["citation"]["archive"].endswith("Abt. Staatsarchiv Sigmaringen")
    assert out["title"] == "Taufregister XII mit Register"


async def test_a_jewish_register_film_is_read_by_its_signature(served, sites, tmp_path):
    route_ddb(sites)
    route_labw(sites)
    out = await call_tool(
        "labw_image", item="J 386 Bü 583", page=2, destination=str(tmp_path / "j.jpg")
    )
    assert out["signature"] == "J 386 Bü 583"
    assert out["citation"]["archive"].endswith("Abt. Hauptstaatsarchiv Stuttgart")
    assert out["item_permalink"] == "https://www.landesarchiv-bw.de/plink/?f=1-446805"


async def test_a_department_that_does_not_hold_the_fonds_is_refused(served, sites, tmp_path):
    out = await call_tool(
        "labw_image", item="StAS F 901 Bd 1511", page=1, destination=str(tmp_path / "x.jpg")
    )
    assert out["error"] == "unknown_signature" and "F 901 Bd 1511" in out["message"]


# --------------------------------------------------------------------------- #
# nrw_search
# --------------------------------------------------------------------------- #
async def test_an_nrw_search_names_archive_signature_dates_and_mets(served, sites):
    portal, _ = route_nrw(sites)
    out = await call_tool(
        "nrw_search",
        query="Geburtsregister Barmen",
        archive="rheinland",
        year_from=1850,
        year_to=1850,
    )
    assert out["total"] == 2 and out["returned"] == 2 and out["next_page"] is None
    first = out["hits"][0]
    assert first["title"] == "Geburtsregister Barmen"
    assert first["institution"] == "Landesarchiv NRW Abteilung Rheinland"
    assert first["signature"] == "PA 2104 Nr. 69 - Band: 1"
    assert first["dates"] == "1850"
    assert first["mets"] == BARMEN_METS and first["readable_by_nrw_image"] is True
    assert first["permalink"].startswith("https://www.archive.nrw.de/ms/search?link=")
    assert "finding-aid entry" in out["note"]
    params = parse_qs(urlsplit(str(portal.calls.last.request.url)).query)
    assert params["archive"] == ["185"] and params["hasDigitalisat"] == ["true"]
    assert params["laufzeitVon"] == ["1850"] and params["laufzeitBis"] == ["1850"]
    assert params["page"] == ["0"] and params["size"] == ["20"]


async def test_an_nrw_search_pages_from_one(served, sites):
    portal, _ = route_nrw(sites)
    out = await call_tool("nrw_search", query="Sterberegister Lemgo", rows=5, page=2)
    params = parse_qs(urlsplit(str(portal.calls.last.request.url)).query)
    assert params["page"] == ["1"] and params["size"] == ["5"]
    assert out["total"] == 33 and out["next_page"] == 3


async def test_an_nrw_search_that_finds_nothing_says_what_a_zero_covers(served, sites):
    route_nrw(sites)
    out = await call_tool("nrw_search", query="Zyxwvutsrq Qwertzuiopp")
    assert out["total"] == 0 and out["hits"] == []
    assert "not a negative" in out["note"]


async def test_an_nrw_search_needs_words(served, sites):
    out = await call_tool("nrw_search", query="   ")
    assert out["error"] == "no_criteria"


async def test_another_archives_viewer_link_is_returned_but_not_read(served, sites):
    answer = fixture("nrw_search_barmen_1850.json")
    answer["searchResult"][0]["disitalisat"] = [
        "https://dfg-viewer.de/show/?tx_dlf[id]=https%3A%2F%2Fwww.duesseldorf.de%2Fstadtarchiv"
        "%2Farchivenrw%2F7%2F0%2F7%2F7_0_7_9_0001%2Fmets.xml"
    ]
    route_nrw(sites, **{"Geburtsregister Barmen": answer})
    out = await call_tool("nrw_search", query="Geburtsregister Barmen")
    hit = out["hits"][0]
    assert hit["readable_by_nrw_image"] is False
    assert hit["mets"].startswith("https://www.duesseldorf.de/")


async def test_a_portal_outage_is_not_an_empty_result(served, sites):
    sites.route(host=NRW_PORTAL_HOST).mock(return_value=httpx.Response(502, text="down"))
    out = await call_tool("nrw_search", query="Geburtsregister Barmen")
    assert out["error"] == "upstream_error" and "Archive in NRW" in out["message"]


# --------------------------------------------------------------------------- #
# nrw_image
# --------------------------------------------------------------------------- #
async def test_an_nrw_page_is_saved_and_cited(served, sites, tmp_path):
    _, images = route_nrw(sites)
    target = tmp_path / "barmen-3.jpg"
    out = await call_tool("nrw_image", item=BARMEN_METS, page=3, destination=str(target))
    assert target.read_bytes() == fixture("nrw_bild_250px.jpg")
    assert (out["width"], out["height"]) == (250, 366)
    assert out["page"] == 3 and out["pages"] == 12
    assert out["citation"]["text"] == (
        "Landesarchiv NRW Abteilung Rheinland, PA 2104 Nr. 69 1, Bild 3"
    )
    assert out["permalink"] == (
        "https://www.archive.nrw.de/ms/search?link="
        "VERZEICHUNGSEINHEIT-Vz_05B2B3A3-B59E-4267-A806-968A3F98FC4D"
    )
    assert out["citation"]["urn"].startswith("urn:nbn:de:danrw:")
    assert "CC BY-SA" in out["rights"]
    assert str(images.calls.last.request.url).endswith("LAV_NRW_R_PA_2104_00069_Bd1_0003.jpg")


async def test_an_nrw_page_is_read_from_a_viewer_link_or_a_bare_path(served, sites, tmp_path):
    route_nrw(sites)
    viewer = "https://dfg-viewer.de/show/?tx_dlf[id]=" + quote(LEMGO_METS, safe="")
    out = await call_tool("nrw_image", item=viewer, page=2, destination=str(tmp_path / "a.jpg"))
    assert out["signature"] == "P 3 / 9 Nr. 260" and out["pages"] == 14
    assert out["citation"]["archive"] == "Landesarchiv NRW Abteilung Ostwestfalen-Lippe"
    out = await call_tool(
        "nrw_image",
        item="Abt_Ostwestfalen-Lippe/P3/P3-09/~002/P3-09_00260",
        page=14,
        destination=str(tmp_path / "b.jpg"),
    )
    assert out["page"] == 14


async def test_an_nrw_register_without_a_page_asks_for_one(served, sites, tmp_path):
    route_nrw(sites)
    out = await call_tool("nrw_image", item=LEMGO_METS, destination=str(tmp_path / "p.jpg"))
    assert out["error"] == "no_page" and out["pages"] == 14


async def test_an_nrw_page_past_the_end_is_refused(served, sites, tmp_path):
    route_nrw(sites)
    out = await call_tool(
        "nrw_image", item=LEMGO_METS, page=15, destination=str(tmp_path / "p.jpg")
    )
    assert out["error"] == "no_such_page" and not (tmp_path / "p.jpg").exists()


async def test_a_mets_file_is_fetched_once_for_many_pages(served, sites, tmp_path):
    _, images = route_nrw(sites)
    for n in (1, 2):
        await call_tool(
            "nrw_image", item=LEMGO_METS, page=n, destination=str(tmp_path / f"{n}.jpg")
        )
    paths = [c.request.url.path.rsplit("/", 1)[-1] for c in images.calls]
    assert paths == ["mets.xml", "OWL_P3-09_00260_00001.jpg", "OWL_P3-09_00260_00002.jpg"]


async def test_an_item_that_is_not_a_landesarchiv_nrw_mets_is_refused(served, sites, tmp_path):
    for item in (
        "https://www.duesseldorf.de/stadtarchiv/archivenrw/7/0/7/7_0_7_9_0001/mets.xml",
        "https://www.landesarchiv-nrw.de/digitalisate/../../etc/mets.xml",
        "https://www.archive.nrw.de/ms/search?link=VERZEICHUNGSEINHEIT-Vz_1",
        "PA 2104 Nr. 69",
    ):
        out = await call_tool("nrw_image", item=item, page=1, destination=str(tmp_path / "x.jpg"))
        assert out["error"] == "unknown_item", item


async def test_an_unknown_mets_file_is_not_found(served, sites, tmp_path):
    route_nrw(sites)
    out = await call_tool(
        "nrw_image",
        item="Abt_Rheinland/PA_9999/~000/00001",
        page=1,
        destination=str(tmp_path / "x.jpg"),
    )
    assert out["error"] == "not_found"


async def test_a_mets_file_naming_an_image_elsewhere_is_not_followed(served, sites, tmp_path):
    hostile = fixture("nrw_mets_p3-09_260.xml").replace(
        "https://www.landesarchiv-nrw.de/data01/", "https://attacker.example/data01/"
    )
    _, images = route_nrw(sites, **{"Abt_Ostwestfalen-Lippe/P3/P3-09/~002/P3-09_00260": hostile})
    out = await call_tool("nrw_image", item=LEMGO_METS, page=1, destination=str(tmp_path / "x.jpg"))
    assert out["error"] == "api_changed" and not (tmp_path / "x.jpg").exists()
    assert images.call_count == 1


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
    assert set(out["hosts"]) == set(ALLOWED_HOSTS) and len(out["hosts"]) == 8
    assert out["seconds_between_requests"][DDB_HOST] == 0.0
    assert out["seconds_between_searches"] == {}
    assert out["seconds_between_volume_downloads"] == {}
    assert out["volume_pdfs"]["volumes"] == 0 and out["volume_pdfs"]["kept_days"] == 3
