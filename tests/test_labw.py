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
        ("F 901 Bd 1511", ("F 901", 1511)),
        ("StAL F 901 Bd. 1511", ("F 901", 1511)),
        ("Abt. Staatsarchiv Ludwigsburg, F 901 Bd 1511", ("F 901", 1511)),
        ("Wü 110 T 1 Nr. 4566", ("Wü 110 T 1", 4566)),
        ("Wue 110 T 1 Nr 4566", ("Wü 110 T 1", 4566)),
        ("StAS Wü 110 T 1 Nr. 4566", ("Wü 110 T 1", 4566)),
        ("J 386 Bü 583", ("J 386", 583)),
        ("HStAS J 386 Bü 583", ("J 386", 583)),
        ("Dep. 1 T 37 Nr. 4", ("Dep. 1 T 37", 4)),
        ("Staatsarchiv Sigmaringen, Dep. 1 T 44 Nr. 3", ("Dep. 1 T 44", 3)),
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
        "StAS F 901 Bd 1",
        "Staatsarchiv Ludwigsburg, J 386 Bü 1",
        "F 9010 Bd 1",
        "Dep. 1 T 3 Nr. 1",
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


def test_the_baden_fonds_are_known_with_their_ids():
    assert labw.FONDS["L 10"].reference == "Abt. Staatsarchiv Freiburg, L 10"
    assert (labw.FONDS["390"].olf_bestand, labw.FONDS["390"].scopeid_besta) == (12390, 5405)


def test_every_fonds_is_known_with_its_ids_and_unit():
    assert list(labw.FONDS) == [
        "L 10",
        "390",
        "F 901",
        "Wü 110 T 1",
        "J 386",
        "Dep. 1 T 37",
        "Dep. 1 T 44",
    ]
    f901 = labw.FONDS["F 901"]
    assert f901.signature(1511) == "Abt. Staatsarchiv Ludwigsburg, F 901 Bd 1511"
    assert (f901.olf_bestand, f901.scopeid_besta) == (18750, 3493)
    assert labw.FONDS["J 386"].signature(583) == "Abt. Hauptstaatsarchiv Stuttgart, J 386 Bü 583"
    assert labw.FONDS["Wü 110 T 1"].place_in == "context"


def test_a_signature_is_matched_to_its_fonds_and_not_a_longer_one():
    assert labw.fonds_of("Abt. Staatsarchiv Ludwigsburg, F 901 Bd 1511").key == "F 901"
    assert labw.fonds_of(
        "Abt. Staatsarchiv Sigmaringen, Wü 110 T 1 {1754: nicht vorhanden}"
    ).key == ("Wü 110 T 1")
    assert labw.fonds_of("Abt. Staatsarchiv Freiburg, L 100 Nr. 1") is None
    assert labw.fonds_of("Abt. Hauptstaatsarchiv Stuttgart, J 389") is None


@pytest.mark.parametrize(
    "olf_id,bestand,signature,department,fonds,count",
    [
        (380914, 18750, "F 901 Bd 1511", "Staatsarchiv Ludwigsburg", "F 901", 290),
        (9165727, 54526, "Wü 110 T 1 Nr. 4566", "Staatsarchiv Sigmaringen", "Wü 110 T 1", 294),
        (1172270, 5632, "J 386 Bü 583", "Hauptstaatsarchiv Stuttgart", "J 386", 137),
    ],
)
def test_the_image_list_of_every_fonds_is_read(
    olf_id, bestand, signature, department, fonds, count
):
    book = labw.parse_thumbnails(
        fixture(f"labw_thumbnails_{olf_id}.html"), olf_bestand=bestand, olf_id=olf_id
    )
    assert book.signature == signature and book.department == department
    assert book.fonds == fonds and len(book.files) == count
    assert labw.fonds_of_book(book) is labw.FONDS[fonds]
    assert book.scopeid_besta == labw.FONDS[fonds].scopeid_besta


def test_a_fonds_title_with_markup_in_the_page_title_is_read():
    book = labw.parse_thumbnails(
        fixture("labw_thumbnails_380914.html"), olf_bestand=18750, olf_id=380914
    )
    assert book.fonds_title.startswith("Katholische Kirchenbücher: Zweitschriften")


def test_a_books_place_is_its_heading_wherever_the_archive_writes_it():
    wue = labw.FONDS["Wü 110 T 1"]
    context = "Evangelische Pfarrämter ... >> U >> Übr - Unl >> Ulm, Münster (Ulm UL)"
    assert labw.place_heading("Taufregister XII", context, wue) == "Ulm, Münster (Ulm UL)"
    f901 = labw.FONDS["F 901"]
    context = "Katholische Kirchenbücher ... >> 20. ORTSBUCHSTABE U >> 20.2 Ulm (St. Michael)"
    assert labw.place_heading("Taufregister", context, f901) == "Ulm (St. Michael)"
    civil = labw.FONDS["Dep. 1 T 37"]
    assert labw.place_heading("Geburtenregister Sigmaringen", "", civil) == "Sigmaringen"
    assert (
        labw.place_heading("Namensverzeichnis zum Sterberegister Sigmaringen", "", civil)
        == "Sigmaringen"
    )
    assert labw.place_heading("Breisach am Rhein", "x", labw.FONDS["J 386"]) == "Breisach am Rhein"


def test_registers_are_read_from_the_title():
    assert labw.registers_of("Taufregister vom 17.5.1849 - 17.5.1867") == ["baptisms"]
    assert labw.registers_of("a) Eheregister vom 1808; b) Taufregister") == [
        "baptisms",
        "marriages",
    ]
    assert labw.registers_of("Trauungsregister vom 1784") == ["marriages"]
    assert labw.registers_of("Sterberegister Sigmaringen") == ["deaths"]
    assert labw.registers_of("Totenregister XI Register (A-K)") == ["deaths"]
    assert labw.registers_of("Familienregister I") == ["family"]
    assert labw.registers_of("Breisach am Rhein FR; Katholische Gemeinde") == []


def test_a_wuerttemberg_book_row_carries_fonds_place_and_confession():
    docs = fixture("ddb_standesbuch_ulm_1850.json")["response"]["docs"]
    doc = next(d for d in docs if d["apd_reference_number"][0].endswith("F 901 Bd 1511"))
    row = labw.book_row(doc, "Ulm")
    assert row["fonds"] == "F 901" and row["signature"] == "F 901 Bd 1511"
    assert row["confessions"] == ["catholic"] and row["registers"] == ["baptisms"]
    assert row["place"] == "Ulm (St. Michael zu den Wengen)"
    assert row["permalink"] == "https://www.landesarchiv-bw.de/plink/?f=2-181572"
    assert "district_court" not in row


def test_the_book_query_searches_headings_only_where_the_place_is_written_there():
    assert labw.books_query("Ulm", ["L 10"]) == 'title:"Ulm"'
    query = labw.books_query("Ulm")
    assert query.startswith('title:"Ulm" OR (apd_reference_number:(')
    assert '"Staatsarchiv Ludwigsburg, F 901"' in query and 'apd_context:"Ulm"' in query
    assert "L 10" not in query
