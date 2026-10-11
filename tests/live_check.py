"""Ask the live sites what the recorded fixtures cannot. Run by hand.

    uv run python -m tests.live_check

Calls paced by the client itself: one request at a time per host, at least
two seconds apart, and the Archive in NRW portal's, APERTUS's and LAGIS's
searches, and APERTUS's volume downloads, at least ten. They check that

* the DDB's version 2 API still answers without a key, and still carries the
  fields the tools read (holder, signature, context, dates, hierarchy,
  children, image links);
* the Landesarchiv's finding aid still reaches the DDB with the Standesbücher
  in it, so a place and a year still find a book, by place and by signature;
* the Landesarchiv's permalinks still redirect as they did, its image lists
  still name every file, and an image still renders, in every register fonds
  (L 10 at Freiburg, 390 at Karlsruhe, F 901 at Ludwigsburg, Wü 110 T 1 and
  the Dep. 1 deposits at Sigmaringen, J 386 at Stuttgart), including an image
  whose file name is out of step with its place in the book;
* Württemberg's volumes are still found by their parish heading, and every
  fonds' signatures still resolve through the DDB;
* the Archive in NRW portal's search still answers keyless JSON with METS
  links for the Landesarchiv NRW's registers, in Rheinland and in
  Ostwestfalen-Lippe, and a METS file still lists page images that download;
* APERTUS still lists the Personenstandsarchiv's units for a place, register
  and years with a form post, finds a unit by signature, opens it, and serves
  its volume as a PDF whose pages are JPEGs: one volume (about 22 MB) is
  downloaded, and a second page of it is read from disk with no request;
* LAGIS's simple search still finds a Hessian register by place, type and
  year, and Arcinsys still resolves its signature to a unit whose METS file
  lists page images that download, by signature and by permalink;
* the allowlist holds: a host off it is refused without a request.

It is not a test module: pytest does not collect it, and CI never runs it,
because the suite must never depend on someone else's server being up. Images
are downloaded to a temporary directory, set as the download folder, and
deleted.

Exit status 0 if every check passed, 1 if any failed.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from german_archives_mcp import server
from german_archives_mcp.client import ARCINSYS_HOST, ArchiveHttp
from german_archives_mcp.config import load_config

#: (tool, arguments, check, what the check means). ``{tmp}`` in an argument
#: is replaced by the temporary directory.
CHECKS: list[tuple[str, dict, Callable[[dict], bool], str]] = [
    (
        "ddb_search",
        {
            "query": "Geburtsregister",
            "archive": "Stadtarchiv Düsseldorf",
            "has_images": True,
            "year_to": 1812,
            "rows": 5,
        },
        lambda r: (
            r["total"] >= 10
            and all(h["institution"] == "Stadtarchiv Düsseldorf" for h in r["hits"])
            and any("Oberkassel" in h.get("context", "") for h in r["hits"])
        ),
        "keyless search: the Stadtarchiv Düsseldorf's digitised birth registers to 1812",
    ),
    (
        "ddb_search",
        {"query": "Zyxwvutsrq Qwertzuiopp"},
        lambda r: r["total"] == 0 and "not a negative" in r["note"],
        "a search that finds nothing says what a zero covers",
    ),
    (
        "ddb_item",
        {"id": "6MOPYW4SNPH5WPLCP74BOLX6PX6NMSQG"},
        lambda r: (
            r["signature"].endswith("9.0003")
            and r["hierarchy"][-1]["title"].endswith("Standesamt Oberkassel")
            and r["images"]["count"] > 100
        ),
        "an entry: signature, its fonds path, and the holder's image links",
    ),
    (
        "ddb_item",
        {"id": "Y6GUU5SWQXL73GUDRXDGTRKNXGNLCBCY", "children": 5},
        lambda r: r.get("grouping_node") and r["children"]["total"] >= 50,
        "a series heading has no record of its own, but parents and children answer",
    ),
    (
        "labw_standesbuch",
        {"place": "Breisach", "year": 1850},
        lambda r: (
            [b["signature"] for b in r["books"]][:1] == ["L 10 Nr. 469"]
            and r["books"][0]["image_count"] > 300
            and any(b["signature"] == "L 10 Nr. 510" for b in r["books"])
        ),
        "Breisach 1850: L 10 Nr. 469 first, with its image count",
    ),
    (
        "labw_standesbuch",
        {"place": "Staufen", "confession": "catholic", "count_images": False},
        lambda r: r["found"] >= 1 and all("catholic" in b["confessions"] for b in r["books"]),
        "Staufen, Catholic books only",
    ),
    (
        "labw_standesbuch",
        {"place": "Spechbach", "count_images": True},
        lambda r: (
            any(b["signature"] == "390 Nr. 1875" for b in r["books"])
            and any(b.get("image_count") for b in r["books"])
        ),
        "north Baden: Spechbach is in GLA Karlsruhe 390, and its images count",
    ),
    (
        "labw_image",
        {
            "item": "L 10 Nr. 510",
            "page": 378,
            "destination": "{tmp}/l10-510-378.jpg",
            "max_pixels": 600,
        },
        lambda r: (
            r["format"] == "jpeg"
            and r["permalink"].endswith("f=5-475861-377")
            and max(r["width"], r["height"]) <= 600
            and r["pages"] >= 380
        ),
        "by signature: Bild 378 of L 10 Nr. 510, whose permalink ends in 377",
    ),
    (
        "labw_image",
        {
            "item": "https://www.landesarchiv-bw.de/plink/?f=5-475861-380",
            "destination": "{tmp}/l10-510-119.jpg",
        },
        lambda r: r["page"] == 119 and r["bytes"] > 50_000,
        "by an image's permalink: 5-475861-380 is Bild 119, at full size",
    ),
    (
        "labw_image",
        {"item": "390 Nr. 1875", "page": 2, "destination": "{tmp}/gla-390-1875-2.jpg"},
        lambda r: (
            r["format"] == "jpeg"
            and r["citation"]["archive"].endswith("Generallandesarchiv Karlsruhe")
        ),
        "the Karlsruhe fonds renders through the same viewer",
    ),
    (
        "labw_image",
        {"item": "5-999999999", "page": 1, "destination": "{tmp}/none.jpg"},
        lambda r: r["error"] == "not_found",
        "a permalink to nothing is not_found, from the archive's own page",
    ),
    (
        "labw_standesbuch",
        {"place": "Ulm", "year": 1850, "count_images": False},
        lambda r: (
            {"Wü 110 T 1", "F 901", "J 386", "390"} <= {b["fonds"] for b in r["books"]}
            and any(
                b["signature"] == "Wü 110 T 1 Nr. 4566" and b["place"].startswith("Ulm")
                for b in r["books"]
            )
            and any(b["signature"] == "F 901 Bd 1511" for b in r["books"])
        ),
        "Ulm 1850: Württemberg's duplicates by parish heading, Jewish films, Baden's Ulm",
    ),
    (
        "labw_standesbuch",
        {"place": "Sigmaringen", "fonds": "Dep. 1 T 37", "year": 1880},
        lambda r: (
            any(b["signature"].startswith("Dep. 1 T 37 Nr.") for b in r["books"])
            and any(b.get("image_count") for b in r["books"])
        ),
        "Sigmaringen's civil registers, one fonds named, with an image count",
    ),
    (
        "labw_image",
        {
            "item": "StAL F 901 Bd 1511",
            "page": 3,
            "destination": "{tmp}/f901-1511-3.jpg",
            "max_pixels": 600,
        },
        lambda r: (
            r["format"] == "jpeg"
            and r["citation"]["archive"].endswith("Staatsarchiv Ludwigsburg")
            and r["permalink"].endswith("f=2-181572-3")
            and "Public Domain" in r["rights"]
        ),
        "F 901 (Ludwigsburg) by signature, through its older viewer's files",
    ),
    (
        "labw_image",
        {
            "item": "Wü 110 T 1 Nr. 4566",
            "page": 1,
            "destination": "{tmp}/wue110-4566-1.jpg",
            "max_pixels": 600,
        },
        lambda r: r["format"] == "jpeg" and r["pages"] > 200,
        "Wü 110 T 1 (Sigmaringen) by signature",
    ),
    (
        "labw_image",
        {"item": "J 386 Bü 583", "page": 2, "destination": "{tmp}/j386-583-2.jpg"},
        lambda r: (
            r["format"] == "jpeg"
            and r["citation"]["archive"].endswith("Hauptstaatsarchiv Stuttgart")
        ),
        "J 386 (Stuttgart) by signature: a film frame, at full size",
    ),
    (
        "labw_image",
        {
            "item": "Dep. 1 T 44 Nr. 3",
            "page": 1,
            "destination": "{tmp}/dep1t44-3-1.jpg",
            "max_pixels": 600,
        },
        lambda r: r["format"] == "jpeg" and r["signature"] == "Dep. 1 T 44 Nr. 3",
        "Dep. 1 T 44 (Sigmaringen-Laiz) by signature",
    ),
    (
        "nrw_search",
        {
            "query": "Geburtsregister Barmen",
            "archive": "rheinland",
            "year_from": 1850,
            "year_to": 1850,
        },
        lambda r: (
            r["total"] >= 1
            and all(h["readable_by_nrw_image"] for h in r["hits"])
            and all(h["signature"].startswith("PA 2104 Nr.") for h in r["hits"])
        ),
        "NRW, Rheinland: Barmen's births of 1850, with METS links this server reads",
    ),
    (
        "nrw_search",
        {
            "query": "Sterberegister Lemgo",
            "archive": "ostwestfalen-lippe",
            "year_from": 1880,
            "year_to": 1880,
            "rows": 5,
        },
        lambda r: r["total"] >= 5 and r["hits"][0]["signature"].startswith("P 3 / 9 Nr."),
        "NRW, Ostwestfalen-Lippe: Lemgo district's deaths of 1880",
    ),
    (
        "nrw_search",
        {"query": "Zyxwvutsrq Qwertzuiopp"},
        lambda r: r["total"] == 0 and "not a negative" in r["note"],
        "an NRW search that finds nothing says what a zero covers",
    ),
    (
        "nrw_image",
        {
            "item": "https://www.landesarchiv-nrw.de/digitalisate/Abt_Rheinland/PA_2104/"
            "~000/00069_Bd1/mets.xml",
            "page": 3,
            "destination": "{tmp}/pa2104-69-3.jpg",
        },
        lambda r: (
            r["format"] == "jpeg"
            and r["pages"] > 800
            and r["permalink"].startswith("https://www.archive.nrw.de/ms/search?link=")
            and "CC BY-SA" in r["rights"]
        ),
        "NRW: a Barmen register page by its METS address, with permalink and licence",
    ),
    (
        "nrw_image",
        {
            "item": "Abt_Ostwestfalen-Lippe/P3/P3-09/~002/P3-09_00260",
            "page": 2,
            "destination": "{tmp}/p3-09-260-2.jpg",
        },
        lambda r: r["width"] > 1000 and r["signature"] == "P 3 / 9 Nr. 260",
        "NRW: a Lemgo-district page by its bare METS path, at full size",
    ),
    (
        "nrw_image",
        {
            "item": "Abt_Rheinland/PA_2104/~000/99999",
            "page": 1,
            "destination": "{tmp}/none-nrw.jpg",
        },
        lambda r: r["error"] == "not_found",
        "NRW: a METS path that does not exist is not_found",
    ),
]

CHECKS += [
    (
        "rlp_search",
        {"place": "Cochem", "register": "death", "year_from": 1880, "year_to": 1881},
        lambda r: (
            r["total"] >= 4
            and {u["fonds"] for u in r["units"]} >= {"657,377", "657,380"}
            and all(u["register"] == "death" for u in r["units"])
        ),
        "APERTUS: Cochem's death registers of 1880-1881, by form post",
    ),
    (
        "rlp_search",
        {"place": "Münstermaifeld", "register": "birth", "year_from": 1850, "year_to": 1850},
        lambda r: r["total"] == 1 and r["units"][0]["signature"] == "Best. 657,335 Nr. 36",
        "APERTUS: an umlaut in the place survives the form post",
    ),
    (
        "rlp_search",
        {"place": "Zyxwvutsrq"},
        lambda r: r["total"] == 0 and "not a negative" in r["note"],
        "APERTUS: a search that finds nothing says what a zero covers",
    ),
    (
        "rlp_image",
        {"item": "Best. 657,349 Nr. 4", "page": 3, "destination": "{tmp}/657-349-4-p3.jpg"},
        lambda r: (
            r["format"] == "jpeg"
            and r["width"] > 2000
            and r["pages"] >= 20
            and r["volume"]["from_disk"] is False
            and r["signature"] == "Best. 657,349 Nr. 4"
            and r["permalink"].startswith("https://apertus.rlp.de/index.php?PLINK=1&ID=")
        ),
        "APERTUS: a page by signature; the volume's PDF is downloaded once",
    ),
    (
        "rlp_image",
        {"item": "Best. 657,349 Nr. 4", "page": 5, "destination": "{tmp}/657-349-4-p5.jpg"},
        lambda r: r["format"] == "jpeg" and r["volume"]["from_disk"] is True,
        "APERTUS: a second page of the same volume comes from disk",
    ),
    (
        "rlp_image",
        {
            "item": "00000000-0000-4000-8000-000000000000",
            "page": 1,
            "destination": "{tmp}/none-rlp.jpg",
        },
        lambda r: r["error"] == "not_found",
        "APERTUS: a GUID that names no unit is not_found",
    ),
    (
        "hessen_search",
        {"place": "Korbach", "register": "birth", "year": 1880},
        lambda r: (
            r["total"] >= 1
            and r["hits"][0]["signature"] == "HStAM 922 Nr. 6013"
            and r["hits"][0]["standesamt"] == "Korbach"
        ),
        "LAGIS: Korbach's births of 1880, with the register's signature",
    ),
    (
        "hessen_search",
        {"place": "Zyxwvutsrq"},
        lambda r: r["total"] == 0 and "not a negative" in r["note"],
        "LAGIS: a search that finds nothing says what a zero covers",
    ),
    (
        "hessen_image",
        {"item": "HStAM 922 Nr. 6013", "page": 2, "destination": "{tmp}/922-6013-2.jpg"},
        lambda r: (
            r["format"] == "jpeg"
            and r["width"] >= 1500
            and r["pages"] > 90
            and r["citation"]["archive"] == "Hessisches Staatsarchiv Marburg"
        ),
        "Arcinsys: a Korbach register page by signature, at full size",
    ),
    (
        "hessen_image",
        {
            "item": f"https://{ARCINSYS_HOST}/arcinsys/detailAction?detailid=v2884088",
            "page": 3,
            "destination": "{tmp}/922-10-3.jpg",
        },
        lambda r: r["format"] == "jpeg" and r["signature"] == "HStAM 922 Nr. 10",
        "Arcinsys: a page by the unit's permalink",
    ),
    (
        "hessen_image",
        {"item": "v999999999", "page": 1, "destination": "{tmp}/none-hla.jpg"},
        lambda r: r["error"] == "not_found",
        "Arcinsys: a unit it will not show is not_found",
    ),
]

#: Checks whose expected answer is a refusal.
REFUSALS = {
    "a permalink to nothing is not_found, from the archive's own page",
    "NRW: a METS path that does not exist is not_found",
    "APERTUS: a GUID that names no unit is not_found",
    "Arcinsys: a unit it will not show is not_found",
}


async def allowlist(http: ArchiveHttp) -> int:
    """A host off the allowlist is refused, with no request sent."""
    before = http.live_calls
    try:
        await http.get_json("https://www.deutsche-digitale-bibliothek.de/", ttl_days=0)
    except Exception as exc:  # noqa: BLE001 - the refusal is the point
        ok = type(exc).__name__ == "HostNotAllowed" and http.live_calls == before
    else:
        ok = False
    print(f"{'PASS' if ok else 'FAIL'}  allowlist: the DDB's portal host is refused unasked")
    return 0 if ok else 1


async def main() -> int:
    cfg = load_config()
    with tempfile.TemporaryDirectory() as cache, tempfile.TemporaryDirectory() as tmp:
        http = ArchiveHttp(
            Path(cache), timeout=cfg.timeout, min_interval=cfg.min_interval, contact=cfg.contact
        )
        server.runtime.config = dataclasses.replace(
            cfg, download_dir=Path(tmp), cache_dir=Path(cache)
        )
        server.runtime.http = http
        failed = await allowlist(http)
        for tool, args, check, meaning in CHECKS:
            args = {
                k: v.replace("{tmp}", tmp) if isinstance(v, str) else v for k, v in args.items()
            }
            result = json.loads((await server.mcp.call_tool(tool, args)).content[0].text)
            try:
                ok = ("error" not in result or meaning in REFUSALS) and bool(check(result))
            except (KeyError, IndexError, TypeError):
                ok = False
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {tool}: {meaning}")
            if not ok:
                print(f"      got: {json.dumps(result, ensure_ascii=False)[:400]}")
        print(f"      requests: {http.hosts_called}")
        await http.aclose()
    total = len(CHECKS) + 1
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
