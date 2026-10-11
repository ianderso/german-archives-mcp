"""Ask the live sites what the recorded fixtures cannot. Run by hand.

    uv run python -m tests.live_check

Calls paced by the client itself: one request at a time per host, the DDB's
at least a second apart and the Landesarchiv's at least two. They check that

* the DDB's version 2 API still answers without a key, and still carries the
  fields the tools read (holder, signature, context, dates, hierarchy,
  children, image links);
* the Landesarchiv's finding aid still reaches the DDB with the Standesbücher
  in it, so a place and a year still find a book, by place and by signature;
* the Landesarchiv's permalinks still redirect as they did, its image lists
  still name every file, and an image still renders, in both fonds (L 10 at
  Freiburg and 390 at Karlsruhe), including an image whose file name is out
  of step with its place in the book;
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
from german_archives_mcp.client import ArchiveHttp
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
]

#: Checks whose expected answer is a refusal.
REFUSALS = {"a permalink to nothing is not_found, from the archive's own page"}


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
        server.runtime.config = dataclasses.replace(cfg, download_dir=Path(tmp))
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
