"""Shared fixtures. Every test runs against mocked sites; nothing touches the network.

The fixtures under ``fixtures/`` are real responses recorded on 2026-10-11
(see docs/API-NOTES.md):

* from the DDB's version 2 API: a search of the Stadtarchiv Düsseldorf's
  digitised civil birth registers (Standesamt Oberkassel, 1798-1816), one of
  those registers with its place in the fonds, the series heading above it
  with its children, a search that finds nothing, and the Landesarchiv
  Baden-Württemberg's finding-aid entries for the registers of Breisach am
  Rhein in 1850 (in L 10 alone, and in every register fonds, which adds the
  Jewish registers of J 386) and of Ulm in 1850 (Württemberg's Protestant and
  Catholic duplicates, Jewish registers, and the two Baden villages called
  Ulm), and books found by signature (L 10 Nr. 510, F 901 Bd 1511, J 386 Bü
  583). The Düsseldorf register's list of 147 images is trimmed to its first
  12.
* from the Landesarchiv Baden-Württemberg's online finding aids: permalink
  redirects, the "no such resource" page, the image lists of four Breisach
  books and of three Ulm books in F 901, Wü 110 T 1 and J 386 (trimmed to the
  page title, the item's heading, the list itself and one thumbnail
  address), and two page images rendered at a few per cent of full size.
* from the Archive in NRW portal: searches for Barmen's birth registers of
  1850 and Lemgo's death registers of 1880, and one that finds nothing; and
  from the Landesarchiv NRW's image server, two METS files (the Barmen
  register trimmed to its first 12 of 827 pages) and one page thumbnail.

The records are registers and finding-aid headings, not people.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from german_archives_mcp import labw, server
from german_archives_mcp.client import (
    DDB_HOST,
    LABW_HOST,
    NRW_IMAGE_HOST,
    NRW_PORTAL_HOST,
    ArchiveHttp,
)
from german_archives_mcp.config import Config

FIXTURES = Path(__file__).parent / "fixtures"

#: Ids used throughout.
OBERKASSEL_1811 = "6MOPYW4SNPH5WPLCP74BOLX6PX6NMSQG"
OBERKASSEL_SERIES = "Y6GUU5SWQXL73GUDRXDGTRKNXGNLCBCY"
L10_510 = "2EF3J2O7CMX2HKZ7YX3GRUT3WIWLCAA5"


def fixture(name: str) -> Any:
    """Load one recorded response: JSON for .json files, bytes for .jpg, text otherwise."""
    path = FIXTURES / name
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".jpg":
        return path.read_bytes()
    return path.read_text(encoding="utf-8")


def make_http(tmp_path: Path, **kwargs) -> ArchiveHttp:
    """A client with no pacing, no host floors and no back-off, caching under ``tmp_path``."""
    options: dict[str, Any] = {
        "min_interval": 0.0,
        "backoff": 0.0,
        "host_floors": {},
        "search_floors": {},
    }
    options.update(kwargs)
    return ArchiveHttp(tmp_path / "cache", **options)


@pytest.fixture
def http(tmp_path) -> ArchiveHttp:
    return make_http(tmp_path)


@pytest.fixture
def served(tmp_path, monkeypatch) -> ArchiveHttp:
    """Install a fast test client as the server's client for the duration of a test."""
    c = make_http(tmp_path)
    monkeypatch.setattr(server.runtime, "http", c)
    monkeypatch.setattr(server.runtime, "config", Config(cache_dir=tmp_path / "cache"))
    return c


@pytest.fixture
def sites():
    """A respx router. Any request it does not expect fails the test."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


def _answer(value: Any) -> httpx.Response:
    if isinstance(value, httpx.Response):
        return value
    if isinstance(value, bytes):
        return httpx.Response(200, content=value, headers={"content-type": "image/jpeg"})
    if isinstance(value, str):
        return httpx.Response(200, text=value, headers={"content-type": "text/html"})
    return httpx.Response(200, json=value)


#: Search answers by the whole ``q`` value.
SEARCHES: dict[str, str] = {
    "Geburtsregister": "ddb_search_duesseldorf_births.json",
    "Zyxwvutsrq Qwertzuiopp": "ddb_search_empty.json",
    'title:"Breisach"': "ddb_standesbuch_breisach_1850.json",
    labw.books_query("Breisach"): "ddb_standesbuch_breisach_1850_all.json",
    labw.books_query("Ulm"): "ddb_standesbuch_ulm_1850.json",
    labw.books_query("Düsseldorf"): "ddb_standesbuch_empty.json",
    'apd_reference_number:"Abt. Staatsarchiv Freiburg, L 10 Nr. 510"': (
        "ddb_signature_l10_510.json"
    ),
    'apd_reference_number:"Abt. Staatsarchiv Ludwigsburg, F 901 Bd 1511"': (
        "ddb_signature_f901_1511.json"
    ),
    'apd_reference_number:"Abt. Hauptstaatsarchiv Stuttgart, J 386 Bü 583"': (
        "ddb_signature_j386_583.json"
    ),
}

#: Item routes by path below /2/items/.
ITEMS: dict[str, Any] = {
    OBERKASSEL_1811: "ddb_item_oberkassel_births.json",
    f"{OBERKASSEL_1811}/parents": "ddb_parents_oberkassel_births.json",
    L10_510: "ddb_item_l10_510.json",
    f"{L10_510}/parents": "ddb_parents_l10_510.json",
    f"{OBERKASSEL_SERIES}/parents": "ddb_parents_oberkassel_series.json",
    f"{OBERKASSEL_SERIES}/children": "ddb_children_oberkassel_series.json",
}


def route_ddb(router: respx.MockRouter, **extra: Any) -> respx.Route:
    """The DDB's API, answering from the recorded fixtures.

    ``extra`` maps a search's ``q`` value, or an item path below /2/items/,
    to a fixture name, a value or an ``httpx.Response``. An unknown item is
    the recorded 404; an unknown search the recorded empty answer.
    """

    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/search/index/search/select"):
            q = request.url.params.get("q", "")
            answer = extra.get(q, SEARCHES.get(q, "ddb_search_empty.json"))
        elif path.startswith("/2/items/"):
            key = path.removeprefix("/2/items/")
            answer = extra.get(key, ITEMS.get(key))
            if answer is None:
                if key.endswith(("/parents", "/children")):
                    answer = {"numberOfResults": 0, "hierarchy": []}
                else:
                    answer = httpx.Response(404, json=fixture("ddb_item_not_found.json"))
        else:
            return httpx.Response(599, text=f"unmocked {request.url}")
        if isinstance(answer, str) and answer.endswith((".json", ".html", ".jpg")):
            answer = fixture(answer)
        return _answer(answer)

    return router.route(host=DDB_HOST).mock(side_effect=respond)


def plink_answer(f: str) -> httpx.Response:
    """The permalink service's answer for one ``f`` value, from the recorded redirects."""
    path = FIXTURES / f"labw_plink_{f}.txt"
    if path.exists():
        status, location = path.read_text().split("\n")[:2]
        return httpx.Response(int(status), headers={"location": location})
    return httpx.Response(200, text=fixture("labw_plink_unknown.html"))


def route_labw(router: respx.MockRouter, **extra: Any) -> respx.Route:
    """The Landesarchiv's online finding aids, answering from the recorded fixtures.

    ``extra`` maps a script name (``plink.php``, ``thumbnails.php``,
    ``bild.php``) to a value or a callable taking the request.
    """

    def respond(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if name in extra:
            answer = extra[name]
            return _answer(answer(request) if callable(answer) else answer)
        params = request.url.params
        if name == "plink.php":
            return plink_answer(params.get("f", ""))
        if name == "thumbnails.php":
            path = FIXTURES / f"labw_thumbnails_{params.get('id', '')}.html"
            if path.exists():
                return _answer(path.read_text(encoding="utf-8"))
            return httpx.Response(404, text="not found")
        if name == "bild.php":
            big = params.get("zoom") == "100"
            return _answer(fixture("labw_bild_243px.jpg" if big else "labw_bild_182px.jpg"))
        return httpx.Response(599, text=f"unmocked {request.url}")

    return router.route(host=LABW_HOST).mock(side_effect=respond)


#: Archive in NRW searches by keyword.
NRW_SEARCHES: dict[str, str] = {
    "Geburtsregister Barmen": "nrw_search_barmen_1850.json",
    "Sterberegister Lemgo": "nrw_search_lemgo_1880.json",
}

#: METS files by their path below /digitalisate/.
NRW_METS: dict[str, str] = {
    "Abt_Rheinland/PA_2104/~000/00069_Bd1": "nrw_mets_pa2104_69bd1.xml",
    "Abt_Ostwestfalen-Lippe/P3/P3-09/~002/P3-09_00260": "nrw_mets_p3-09_260.xml",
}

#: A METS address in the fixtures.
BARMEN_METS = f"https://{NRW_IMAGE_HOST}/digitalisate/Abt_Rheinland/PA_2104/~000/00069_Bd1/mets.xml"
LEMGO_METS = (
    f"https://{NRW_IMAGE_HOST}/digitalisate/Abt_Ostwestfalen-Lippe/P3/P3-09/~002/"
    "P3-09_00260/mets.xml"
)


def route_nrw(router: respx.MockRouter, **extra: Any) -> tuple[respx.Route, respx.Route]:
    """The Archive in NRW portal and the Landesarchiv NRW's image server, from the fixtures.

    ``extra`` maps a keyword, a METS path, or ``"image"`` to a value or an
    ``httpx.Response``. An unknown keyword is the recorded empty answer; an
    unknown METS path a 404.
    """

    def portal(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/sufservice/api/search":
            return httpx.Response(599, text=f"unmocked {request.url}")
        keyword = request.url.params.get("keyword", "")
        answer = extra.get(keyword, NRW_SEARCHES.get(keyword, "nrw_search_empty.json"))
        return _answer(fixture(answer) if isinstance(answer, str) else answer)

    def images(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/digitalisate/") and path.endswith("/mets.xml"):
            key = path.removeprefix("/digitalisate/").removesuffix("/mets.xml")
            answer = extra.get(key, NRW_METS.get(key))
            if answer is None:
                return httpx.Response(404, text="<html><title>404 Not Found</title></html>")
            if isinstance(answer, str):
                text = fixture(answer) if answer.endswith(".xml") else answer
                return httpx.Response(200, text=text, headers={"content-type": "application/xml"})
            return _answer(answer)
        if path.endswith(".jpg"):
            return _answer(extra.get("image", fixture("nrw_bild_250px.jpg")))
        return httpx.Response(599, text=f"unmocked {request.url}")

    return (
        router.route(host=NRW_PORTAL_HOST).mock(side_effect=portal),
        router.route(host=NRW_IMAGE_HOST).mock(side_effect=images),
    )


async def call_tool(tool_name: str, /, **arguments) -> dict:
    """Invoke a tool the way a client does, so Field defaults are resolved."""
    result = await server.mcp.call_tool(tool_name, arguments)
    return json.loads(result.content[0].text)


# --------------------------------------------------------------------------- #
# Argument building for whole-surface sweeps
# --------------------------------------------------------------------------- #
#: Errors a tool returns from its own input checks, before any work. A sweep
#: that gets one of these has not tested what it thinks it has.
LOCAL_VALIDATION_ERRORS = frozenset(
    {
        "no_criteria",
        "invalid_argument",
        "invalid_id",
        "invalid_place",
        "unknown_signature",
        "unknown_item",
        "no_such_directory",
        "destination_exists",
        "relative_destination",
        "bad_extension",
        "hidden_path",
        "protected_location",
        "outside_download_dir",
        "bad_size",
    }
)

#: Arguments that carry each tool past its own checks. The image tools'
#: destinations are filled in per test, under tmp_path.
VALID_ARGS: dict[str, dict] = {
    "ddb_search": {"query": "Geburtsregister"},
    "ddb_item": {"id": OBERKASSEL_1811},
    "labw_standesbuch": {"place": "Breisach", "year": 1850},
    "labw_image": {"item": "L 10 Nr. 510", "page": 378},
    "nrw_search": {"query": "Geburtsregister Barmen"},
    "nrw_image": {"item": BARMEN_METS, "page": 2},
    "cache_status": {},
}

#: Tools that write a file and so need a destination.
IMAGE_TOOLS = frozenset({"labw_image", "nrw_image"})


def valid_args(tool_name: str, tmp_path: Path) -> dict:
    """VALID_ARGS for one tool, with a fresh destination for the image tools."""
    args = dict(VALID_ARGS[tool_name])
    if tool_name in IMAGE_TOOLS:
        args["destination"] = str(tmp_path / f"sweep-{len(list(tmp_path.iterdir()))}.jpg")
    return args


def assert_reached_body(tool_name: str, result) -> None:
    """Fail if a sweep stopped at input validation instead of the tool's body."""
    if isinstance(result, dict) and result.get("error") in LOCAL_VALIDATION_ERRORS:
        raise AssertionError(
            f"{tool_name} rejected the sweep's arguments with {result['error']!r}; "
            f"update VALID_ARGS in tests/conftest.py. Message: {result.get('message')!r}"
        )
