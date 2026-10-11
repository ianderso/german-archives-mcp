"""Reading the Landesarchiv's signatures, permalinks and image lists."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from german_archives_mcp import labw

from .conftest import fixture


@pytest.mark.parametrize(
    "text,expected",
    [
        ("L 10 Nr. 510", ("L 10", 510)),
        ("L10 Nr 510", ("L 10", 510)),
        ("Abt. Staatsarchiv Freiburg, L 10 Nr. 510", ("L 10", 510)),
        ("Staatsarchiv Freiburg L 10 Nr. 510", ("L 10", 510)),
        ("390 Nr. 1875", ("390", 1875)),
        ("GLA 390 Nr. 1875", ("390", 1875)),
        ("Abt. Generallandesarchiv Karlsruhe, 390 Nr. 1875", ("390", 1875)),
    ],
)
def test_signatures_are_read_in_their_usual_forms(text, expected):
    fonds, number = labw.parse_signature(text)
    assert (fonds.key, number) == expected


@pytest.mark.parametrize(
    "text",
    [
        "L 100 Nr. 5",
        "B 10 Nr. 5",
        "Generallandesarchiv Karlsruhe, L 10 Nr. 510",
        "Staatsarchiv Freiburg, 390 Nr. 1",
        "L 10 Nr. 510; rm -rf",
        "",
    ],
)
def test_other_signatures_are_not_guessed_at(text):
    assert labw.parse_signature(text) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://www.landesarchiv-bw.de/plink/?f=5-475861", (5, 475861, None)),
        ("https://www.landesarchiv-bw.de/plink/?f=5-475861-377", (5, 475861, 377)),
        ("http://www.landesarchiv-bw.de/plink/?f=4-1217403-1", (4, 1217403, 1)),
        ("https://www2.landesarchiv-bw.de/ofs21/plink.php?f=5-475861", (5, 475861, None)),
        ("5-475861-380", (5, 475861, 380)),
    ],
)
def test_permalinks_are_read_in_every_form(text, expected):
    assert labw.parse_permalink(text) == expected


@pytest.mark.parametrize(
    "text",
    ["https://evil.example/plink/?f=5-475861", "5-475861-377-1", "f=5-x", "L 10 Nr. 510"],
)
def test_anything_else_is_not_a_permalink(text):
    assert labw.parse_permalink(text) is None


def test_a_permalink_redirect_names_the_fonds_and_the_item():
    assert labw.parse_location(
        "olf/struktur.php?bestand=10028&sprungId=2239944&letztesLimit=suchen"
    ) == {"bestand": 10028, "olf_id": 2239944, "file": None}
    assert labw.parse_location(
        "bild_zoom/plink_screen.php?bestand=10028&id=2239944"
        "&gewaehlteSeite=05_0000475861_0378_5-475861-377.png"
    ) == {"bestand": 10028, "olf_id": 2239944, "file": "05_0000475861_0378_5-475861-377.png"}
    assert labw.parse_location("index.php") is None
    assert labw.parse_location("olf/struktur.php?bestand=x&sprungId=1") is None


def test_the_image_list_gives_every_file_in_order():
    book = labw.parse_thumbnails(
        fixture("labw_thumbnails_2239944.html"), olf_bestand=10028, olf_id=2239944
    )
    assert book.department == "Staatsarchiv Freiburg" and book.fonds == "L 10"
    assert book.fonds_title == "Standesbücher"
    assert book.signature == "L 10 Nr. 510"
    assert book.title.startswith("Niederrimsingen, Breisach am Rhein FR")
    assert (book.archive, book.scope, book.scopeid_besta) == (5, 475861, 5698)
    assert len(book.files) == 380
    # Bild 119 is an image added later: its file ends in 380, and every image
    # after it is numbered one behind its place.
    assert book.files[118] == "05_0000475861_0119_5-475861-380.jpg"
    assert book.files[377] == "05_0000475861_0378_5-475861-377.png"
    assert book.full_signature == "Abt. Staatsarchiv Freiburg, L 10 Nr. 510"


def test_an_unreadable_page_is_not_a_book():
    assert labw.parse_thumbnails("<html></html>", olf_bestand=1, olf_id=1) is None


def test_a_hostile_option_value_is_never_taken_for_an_image():
    page = fixture("labw_thumbnails_2239944.html").replace(
        '<option value="">Bitte wählen</option>',
        '<option value="../../etc/passwd">x</option><option value="a.png">y</option>',
    )
    book = labw.parse_thumbnails(page, olf_bestand=10028, olf_id=2239944)
    assert len(book.files) == 380 and "../../etc/passwd" not in book.files


def test_an_images_permalink_number_is_the_last_number_of_its_file():
    assert labw.image_id("05_0000475861_0378_5-475861-377.png") == 377
    assert labw.image_id("05_0000475861_0119_5-475861-380.jpg") == 380
    assert labw.image_id("nonsense.png") is None


def test_the_image_address_names_the_archives_own_file():
    book = labw.parse_thumbnails(
        fixture("labw_thumbnails_2239944.html"), olf_bestand=10028, olf_id=2239944
    )
    url = labw.bild_url(book, book.files[377], zoom=50)
    parts = urlsplit(url)
    params = parse_qs(parts.query, keep_blank_values=True)
    assert parts.hostname == "www2.landesarchiv-bw.de"
    assert parts.path == "/ofs21/bild_zoom/bild.php"
    assert params["zoom"] == ["50"] and params["scopeid_besta"] == ["5698"]
    assert params["originalBilddatei"] == [
        "/data/bildcms/internetbilder/archiv_5/olf/bestand_0000005698/"
        "titlaufn_0000475861/05_0000475861_0378_5-475861-377.png"
    ]


def test_the_image_address_refuses_a_file_name_the_archive_does_not_use():
    book = labw.parse_thumbnails(
        fixture("labw_thumbnails_2239944.html"), olf_bestand=10028, olf_id=2239944
    )
    with pytest.raises(ValueError):
        labw.bild_url(book, "../../../etc/passwd")


def test_confessions_are_read_from_the_title():
    assert labw.confessions_of(
        "Breisach am Rhein FR; Katholische Gemeinde: Standesbücher 1848-1854 Breisach am "
        "Rhein FR; Israelitische Gemeinde: Standesbücher 1848-1854"
    ) == ["catholic", "jewish"]
    assert labw.confessions_of("X; Evangelische Gemeinde") == ["protestant"]
    assert labw.confessions_of("X; Altkatholische Gemeinde") == ["old catholic"]
    assert labw.confessions_of("X; Standesbuch") == []


def test_the_district_court_is_read_from_the_context():
    assert labw.court_of("Standesbücher >> Breisach; Amtsgericht") == "Breisach"
    assert labw.court_of("Standesbücher >> Amtsgerichtsbezirk Heidelberg") == "Heidelberg"


def test_a_book_is_the_places_own_when_its_title_begins_with_it():
    assert labw.named_first("Breisach am Rhein FR; Katholische Gemeinde", "Breisach")
    assert labw.named_first("Breisach am Rhein FR; Katholische Gemeinde", "Breisach am Rhein")
    assert not labw.named_first("Niederrimsingen, Breisach am Rhein FR; Kath.", "Breisach")


def test_a_place_argument_is_held_to_letters_and_spaces():
    assert labw.valid_place("  Breisach   am Rhein ") == "Breisach am Rhein"
    assert labw.valid_place("St. Märgen") == "St. Märgen"
    for bad in ("", "x", 'a" OR title:*', "a\\b", "a" * 81):
        assert labw.valid_place(bad) is None


def test_a_book_row_carries_signature_years_court_and_permalink():
    doc = fixture("ddb_standesbuch_breisach_1850.json")["response"]["docs"][1]
    row = labw.book_row(doc, "Breisach")
    assert row["signature"] == "L 10 Nr. 510"
    assert row["archive"] == "Landesarchiv Baden-Württemberg, Abt. Staatsarchiv Freiburg"
    assert row["years"] == "1847-1870"
    assert row["district_court"] == "Breisach"
    assert row["permalink"] == "https://www.landesarchiv-bw.de/plink/?f=5-475861"
    assert row["place_named_first"] is False


def test_the_citation_names_archive_signature_image_and_permalink():
    book = labw.parse_thumbnails(
        fixture("labw_thumbnails_2239944.html"), olf_bestand=10028, olf_id=2239944
    )
    cite = labw.citation(book, 119, book.files[118])
    assert cite["text"] == (
        "Landesarchiv Baden-Württemberg, Abt. Staatsarchiv Freiburg, L 10 Nr. 510, Bild 119"
    )
    assert cite["permalink"] == "https://www.landesarchiv-bw.de/plink/?f=5-475861-380"


def test_the_two_fonds_are_known_with_their_ids():
    assert labw.FONDS["L 10"].reference == "Abt. Staatsarchiv Freiburg, L 10"
    assert (labw.FONDS["390"].olf_bestand, labw.FONDS["390"].scopeid_besta) == (12390, 5405)
