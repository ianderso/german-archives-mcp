"""Building DDB requests and shaping its answers, against recorded responses."""

from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest

from german_archives_mcp import ddb

from .conftest import L10_510, OBERKASSEL_1811, OBERKASSEL_SERIES, fixture


def test_day_numbers_match_what_the_ddb_stores():
    """1847-01-01 is stored as 674239 (observed on L 10 Nr. 510)."""
    assert ddb.day_number(date(1847, 1, 1)) == 674239
    assert ddb.from_day_number([683004]) == date(1870, 12, 31)
    assert ddb.from_day_number(None) is None and ddb.from_day_number("x") is None


@pytest.mark.parametrize(
    "raw",
    [
        OBERKASSEL_1811,
        f"https://www.deutsche-digitale-bibliothek.de/item/{OBERKASSEL_1811}",
        f"https://www.archivportal-d.de/item/{OBERKASSEL_1811}?query=x",
        f"https://api.deutsche-digitale-bibliothek.de/2/items/{OBERKASSEL_1811}",
    ],
)
def test_an_id_is_read_from_an_id_or_an_entry_address(raw):
    assert ddb.item_id(raw) == OBERKASSEL_1811


@pytest.mark.parametrize(
    "raw", ["", "abc", "6mopyw4snph5wplcp74bolx6px6nmsqg", "https://x.org/item/A"]
)
def test_anything_else_is_not_an_id(raw):
    assert ddb.item_id(raw) is None


def test_query_syntax_that_reaches_fields_or_parameters_is_escaped():
    assert ddb.escape_query('{!join from=x}title:"a" [* TO *]') == (
        r'\{\!join from=x\}title\:"a" \[* TO *\]'
    )
    assert ddb.escape_query("Standesamt  OR\tGeburtsregister*") == "Standesamt OR Geburtsregister*"


def test_a_name_for_a_string_field_escapes_everything_but_letters():
    assert ddb.escape_term("Stadtarchiv Düsseldorf") == r"Stadtarchiv\ Düsseldorf"
    assert ddb.escape_term('a"b*') == r"a\"b\*"


def test_years_filter_by_overlap():
    assert ddb.year_filters(1850, 1850) == [
        f"begin_time:[* TO {ddb.day_number(date(1850, 12, 31))}]",
        f"end_time:[{ddb.day_number(date(1850, 1, 1))} TO *]",
    ]
    assert ddb.year_filters(None, None) == []


def test_a_search_address_carries_every_filter_and_the_page():
    url = ddb.search_url(query="", filters=["a:b", "c:d"], start=40, rows=20)
    params = parse_qs(urlsplit(url).query)
    assert params["q"] == ["*:*"] and params["fq"] == ["a:b", "c:d"]
    assert (params["start"], params["rows"]) == (["40"], ["20"])
    assert urlsplit(url).hostname == "api.deutsche-digitale-bibliothek.de"


def test_a_hit_names_holder_signature_dates_context_and_level():
    doc = fixture("ddb_search_duesseldorf_births.json")["response"]["docs"][0]
    hit = ddb.hit(doc)
    assert hit["id"] == OBERKASSEL_1811
    assert hit["institution"] == "Stadtarchiv Düsseldorf"
    assert hit["signature"] == "7-0-7 Standesamtsregister: Geburtsurkunden, 7-0-7- 9.0003"
    assert hit["dates"] == "1811-1816"
    assert hit["context"].endswith("Standesamt Oberkassel")
    assert hit["level"] == "unit (Verzeichnungseinheit)"
    assert hit["has_images"] is True
    assert hit["archivportal_url"].endswith(OBERKASSEL_1811)


def test_the_holder_is_the_data_provider_not_an_aggregator():
    doc = {"provider": ["Archive in NRW", "Stadtarchiv X"], "dataprovider_fct": ["Stadtarchiv X"]}
    assert ddb.holder_of(doc) == "Stadtarchiv X"


def test_a_landesarchiv_entry_names_its_permalink_scope():
    doc = fixture("ddb_signature_l10_510.json")["response"]["docs"][0]
    assert ddb.labw_scope(doc) == (5, 475861)
    assert ddb.labw_scope({"provider_item_id": "ID_AKTE_1248488"}) is None


def test_an_entry_gives_signature_fonds_context_dates_and_fields():
    out = ddb.item(fixture("ddb_item_oberkassel_births.json"))
    assert out["title"] == "Geburtsregister Standesamt Oberkassel"
    assert out["institution"]["name"] == "Stadtarchiv Düsseldorf"
    assert out["institution"]["isil"] == "DE-Due75"
    assert out["signature"].endswith("7-0-7- 9.0003")
    assert out["dates"] == "1811-1816"
    assert out["context"].startswith("Standesamtsregister: Geburtsurkunden")
    assert "Enthältvermerke" in out["fields"]


def test_an_entrys_images_are_links_to_the_holders_files():
    count, listed = ddb.images(fixture("ddb_item_oberkassel_births.json"), 5)
    assert count == 12 and len(listed) == 5
    assert [r["position"] for r in listed] == [1, 2, 3, 4, 5]
    assert listed[0]["url"].startswith("https://www.duesseldorf.de/stadtarchiv/")
    assert listed[0]["license"] == "http://rightsstatements.org/vocab/CNE/1.0/"


def test_the_holders_page_is_the_records_origin():
    assert ddb.holder_page(fixture("ddb_item_l10_510.json")) == (
        "https://www.landesarchiv-bw.de/plink/?f=5-475861"
    )


def test_markup_in_a_value_is_removed():
    assert ddb.plain('Es gelten die <a href="x">Nutzungsbedingungen</a>.') == (
        "Es gelten die Nutzungsbedingungen ."
    )


def test_the_hierarchy_runs_from_the_archive_down_to_the_parent():
    above, own = ddb.hierarchy(fixture("ddb_parents_l10_510.json"), L10_510)
    assert [h["title"] for h in above][:1] == ["Landesarchiv Baden-Württemberg"]
    assert above[-1]["title"] == "Breisach; Amtsgericht"
    assert above[-2]["level"] == "fonds (Bestand)"
    assert own["leaf"] is True


def test_a_grouping_nodes_own_row_says_so():
    above, own = ddb.hierarchy(fixture("ddb_parents_oberkassel_series.json"), OBERKASSEL_SERIES)
    assert own["aggregationEntity"] is True and own["leaf"] is False
    assert above[-1]["title"] == "Standesamtsregister: Geburtsurkunden"


def test_children_come_in_the_finding_aids_order():
    total, rows = ddb.children(fixture("ddb_children_oberkassel_series.json"))
    assert total == 55 and len(rows) == 3
    # Recorded out of order (positions 01145, 01126, 01118); sorted by position.
    assert rows[0]["id"] == "QVNWQV667LRR5MAKJCWV6RZQIIWLRJGC"
    assert rows[-1]["title"] == "Geburtsregister Standesamt Oberkassel 1-164"
    assert rows[0]["has_children"] is False
