"""The Landesarchiv Baden-Württemberg's Standesbücher: finding a book, reading a page.

Baden kept civil duplicates of its parish registers from 1810 to 1870, one
book per parish and confession for a span of years. The Landesarchiv holds
them in two fonds, both fully digitised:

* **L 10** at the Staatsarchiv Freiburg: south Baden (the Freiburg district).
* **390** at the Generallandesarchiv Karlsruhe: north Baden (the Karlsruhe
  district, with Mannheim, Heidelberg and Pforzheim).

Finding a book uses the Landesarchiv's own finding aid as it delivers it to
the DDB (CC0): one keyless query names the books whose title has the place,
with signature, years and the scope id behind the permalink. Reading a page
uses the Landesarchiv's online finding-aid system (``www2``, "OLF"):

1. ``/ofs21/plink.php?f=5-475861`` redirects to the item's structure page,
   naming the fonds (``bestand``) and the item's internal id (``sprungId``).
   ``f=5-475861-377`` redirects to one image instead.
2. ``/ofs21/bild_zoom/thumbnails.php?bestand=…&id=…`` lists every image of
   the book, in order, by file name: "Bild 378" is the 378th entry, and its
   file name need not end in 378 (an image inserted later breaks the run).
3. ``/ofs21/bild_zoom/bild.php?…&originalBilddatei=…`` renders one image as a
   JPEG at a zoom percentage; 100 is the viewer's full size.

Observed 2026-10-11; see docs/API-NOTES.md.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from .client import LABW_HOST
from .ddb import escape_term, first, from_day_number, search_url

#: The archive's name, first in every citation.
ARCHIVE = "Landesarchiv Baden-Württemberg"

#: The holder's name as the DDB writes it.
DDB_PROVIDER = "Landesarchiv Baden-Württemberg"

#: Base of the online finding-aid system.
OFS = f"https://{LABW_HOST}/ofs21"


@dataclass(frozen=True)
class Fonds:
    """One Standesbücher fonds: where it is, and how the OLF names it."""

    key: str
    archive: int
    department: str
    region: str
    olf_bestand: int
    scopeid_besta: int

    @property
    def reference(self) -> str:
        """The signature's prefix as the archive writes it: ``Abt. Staatsarchiv Freiburg, L 10``."""
        return f"Abt. {self.department}, {self.key}"


#: The two fonds of Baden Standesbücher. ``olf_bestand`` and ``scopeid_besta``
#: are the OLF's ids for the fonds (seen in its permalink redirects and image
#: addresses, 2026-10-11).
FONDS: dict[str, Fonds] = {
    "L 10": Fonds("L 10", 5, "Staatsarchiv Freiburg", "south Baden", 10028, 5698),
    "390": Fonds("390", 4, "Generallandesarchiv Karlsruhe", "north Baden", 12390, 5405),
}

#: The years the Standesbücher cover. A few north Baden books begin earlier.
FIRST_YEAR, LAST_YEAR = 1810, 1870

#: Confessions as the titles write them.
CONFESSIONS: dict[str, re.Pattern[str]] = {
    "catholic": re.compile(r"(?<!alt)(?<!alt-)katholisch", re.I),
    "protestant": re.compile(r"evangelisch|lutherisch|reformiert|protestantisch", re.I),
    "jewish": re.compile(r"israelitisch|jüdisch", re.I),
    "old catholic": re.compile(r"alt-?katholisch", re.I),
    "mennonite": re.compile(r"mennonit", re.I),
}

#: A place as a tool argument may give it.
_PLACE = re.compile(r"[\w .'()\-]{2,80}")

#: An image file in the OLF: ``05_0000475861_0378_5-475861-377.png``.
_FILE = re.compile(r"(\d{2})_(\d{10})_(\d{4,5})_(\d)-(\d{1,10})-(\d{1,6})\.(png|jpe?g|tiff?)")

#: A signature: optional department, the fonds, the number.
_SIGNATURE = re.compile(
    r"""^\s*
    (?:abt\.?\s*)?
    (?P<dept>staatsarchiv\s+freiburg|generallandesarchiv\s+karlsruhe|gla(?:\s+karlsruhe)?
       |sta(?:\s+freiburg)?)?
    \s*,?\s*
    (?P<fonds>l\s*10|390)
    \s*,?\s*nr\.?\s*
    (?P<number>\d{1,6})\s*$""",
    re.I | re.X,
)

#: A permalink, in any of its forms, or its bare ``f`` value.
_PERMALINK = re.compile(
    r"""^\s*(?:
      (?:https?://)?(?:www2?\.)?landesarchiv-bw\.de/(?:plink/?\?|ofs21/plink\.php\?)(?:.*&)?f=
    )?
    (?P<archive>\d)-(?P<scope>\d{1,10})(?:-(?P<image>\d{1,6}))?\s*$""",
    re.I | re.X,
)


class NotStandesbuch(ValueError):
    """Raised for a signature this server cannot resolve without a permalink."""


@dataclass
class Book:
    """One digitised item as the OLF's thumbnail page describes it."""

    archive: int
    scope: int
    olf_bestand: int
    olf_id: int
    department: str
    fonds: str
    fonds_title: str
    signature: str
    title: str
    scopeid_besta: int
    files: list[str] = field(default_factory=list)

    @property
    def full_signature(self) -> str:
        """``Abt. Staatsarchiv Freiburg, L 10 Nr. 510``."""
        return f"Abt. {self.department}, {self.signature}" if self.department else self.signature

    @property
    def permalink(self) -> str:
        """The item's permalink."""
        return permalink(self.archive, self.scope)


def permalink(archive: int, scope: int, image: int | None = None) -> str:
    """The Landesarchiv's public permalink for an item, or for one of its images."""
    suffix = f"-{image}" if image is not None else ""
    return f"https://www.landesarchiv-bw.de/plink/?f={archive}-{scope}{suffix}"


def plink_url(archive: int, scope: int, image: int | None = None) -> str:
    """The permalink service on ``www2``, which the public permalink redirects to."""
    suffix = f"-{image}" if image is not None else ""
    return f"{OFS}/plink.php?f={archive}-{scope}{suffix}"


def thumbnails_url(olf_bestand: int, olf_id: int) -> str:
    """The page listing every image of an item."""
    return f"{OFS}/bild_zoom/thumbnails.php?bestand={olf_bestand}&id={olf_id}"


def bild_url(book: Book, file: str, *, zoom: int = 100, quality: int = 85) -> str:
    """The address that renders one image of ``book`` as a JPEG."""
    if not _FILE.fullmatch(file):
        raise ValueError(f"not an image file name the archive uses: {file!r}")
    original = (
        f"/data/bildcms/internetbilder/archiv_{book.archive}/olf/"
        f"bestand_{book.scopeid_besta:010d}/titlaufn_{book.scope:010d}/{file}"
    )
    params = [
        ("drehen", ""),
        ("zoom", str(zoom)),
        ("gamma", "1"),
        ("jpegQualitaetZoombild", str(quality)),
        ("scopeid_besta", str(book.scopeid_besta)),
        ("originalBilddatei", original),
    ]
    return f"{OFS}/bild_zoom/bild.php?{urlencode(params, quote_via=quote, safe='')}"


def image_id(file: str) -> int | None:
    """The number an image's permalink ends in: the last number of its file name."""
    match = _FILE.fullmatch(file)
    return int(match.group(6)) if match else None


def parse_signature(text: str) -> tuple[Fonds, int] | None:
    """The fonds and number of an L 10 or 390 signature, or None."""
    match = _SIGNATURE.match(text or "")
    if not match:
        return None
    fonds = FONDS["L 10" if match.group("fonds").lower().startswith("l") else "390"]
    dept = (match.group("dept") or "").lower()
    if dept:
        freiburg = dept.startswith(("staatsarchiv", "sta"))
        if freiburg != (fonds.key == "L 10"):
            return None
    return fonds, int(match.group("number"))


def parse_permalink(text: str) -> tuple[int, int, int | None] | None:
    """(archive, scope id, image id or None) from a permalink or its ``f`` value."""
    match = _PERMALINK.match(text or "")
    if not match:
        return None
    image = match.group("image")
    return int(match.group("archive")), int(match.group("scope")), int(image) if image else None


def parse_location(location: str) -> dict[str, Any] | None:
    """What a permalink redirect names: the fonds, the item's OLF id, and any image file."""
    parts = urlsplit(location or "")
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    path = parts.path
    try:
        bestand = int(query.get("bestand", ""))
    except ValueError:
        return None
    if path.endswith("struktur.php") and query.get("sprungId", "").isdigit():
        return {"bestand": bestand, "olf_id": int(query["sprungId"]), "file": None}
    if path.endswith("plink_screen.php") and query.get("id", "").isdigit():
        file = query.get("gewaehlteSeite", "")
        return {
            "bestand": bestand,
            "olf_id": int(query["id"]),
            "file": file if _FILE.fullmatch(file) else None,
        }
    return None


def no_such_resource(text: str) -> bool:
    """Whether a permalink answered with the archive's "no such resource" page."""
    # The live page writes "existiert <b>keine Ressource</b>".
    return "existiert keine Ressource" in _plain(text or "")


def parse_thumbnails(text: str, *, olf_bestand: int, olf_id: int) -> Book | None:
    """An item's description and image list from its thumbnail page, or None."""
    title_tag = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    head = _plain(title_tag.group(1)) if title_tag else ""
    # "Staatsarchiv Freiburg - Bestand L 10: Standesbücher - Dokumente - Auswahl"
    m = re.match(r"(?P<dept>.+?) - Bestand (?P<fonds>[^:]+): (?P<ftitle>.+?) - Dokumente", head)
    block = re.search(r'<div id="titelaufnahme">(.*?)</div>', text, re.S | re.I)
    if not block:
        return None
    cells = [_plain(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", block.group(1), re.S | re.I)]
    cells = [c for c in cells if c]
    if not cells:
        return None
    department = m.group("dept").strip() if m else ""
    fonds = m.group("fonds").strip() if m else ""
    heading = cells[0]
    signature = heading[len(department) :].strip() if heading.startswith(department) else heading
    select = re.search(r'<select[^>]+name="gewaehlteSeite"[^>]*>(.*?)</select>', text, re.S | re.I)
    files = (
        [
            f
            for f in re.findall(r'<option[^>]*value="([^"]+)"', select.group(1))
            if _FILE.fullmatch(f)
        ]
        if select
        else []
    )
    besta = re.search(r"scopeid_besta=(\d+)", text)
    if files:
        fm = _FILE.fullmatch(files[0])
        archive, scope = int(fm.group(4)), int(fm.group(5))
    else:
        archive = scope = 0
    return Book(
        archive=archive,
        scope=scope,
        olf_bestand=olf_bestand,
        olf_id=olf_id,
        department=department,
        fonds=fonds,
        fonds_title=m.group("ftitle").strip() if m else "",
        signature=signature,
        title=cells[1] if len(cells) > 1 else "",
        scopeid_besta=int(besta.group(1)) if besta else 0,
        files=files,
    )


def _plain(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ").split())


# --------------------------------------------------------------------------- #
# Finding a book through the DDB's copy of the finding aid
# --------------------------------------------------------------------------- #
def valid_place(place: str) -> str | None:
    """A place argument, tidied, or None if it is not a plausible place name."""
    text = " ".join((place or "").split())
    return text if _PLACE.fullmatch(text) else None


def fonds_filter() -> str:
    """Keep the two Standesbücher fonds."""
    refs = " OR ".join(f'"{f.department}, {f.key}"' for f in FONDS.values())
    return f"apd_reference_number:({refs})"


def provider_filter() -> str:
    """Keep the Landesarchiv's own entries."""
    return f"provider_fct:{escape_term(DDB_PROVIDER)}"


def books_url(place: str, year_filters: list[str], rows: int) -> str:
    """The DDB search for the Standesbücher whose title names ``place``."""
    phrase = place.replace("\\", " ").replace('"', " ")
    return search_url(
        query=f'title:"{phrase}"',
        filters=[provider_filter(), fonds_filter(), *year_filters],
        start=0,
        rows=rows,
        fields="id,title,apd_reference_number,apd_context,begin_time,end_time,provider_item_id",
    )


def signature_url(fonds: Fonds, number: int) -> str:
    """The DDB search for one book by its signature."""
    return search_url(
        query=f'apd_reference_number:"{fonds.reference} Nr. {number}"',
        filters=[provider_filter()],
        start=0,
        rows=5,
        fields="id,title,apd_reference_number,begin_time,end_time,provider_item_id",
    )


def confessions_of(title: str) -> list[str]:
    """The confessions a book's title names, in the order of :data:`CONFESSIONS`."""
    return [name for name, pattern in CONFESSIONS.items() if pattern.search(title or "")]


def court_of(context: str) -> str:
    """The district court (Amtsgericht) a book is filed under, from its context path."""
    last = (context or "").split(">>")[-1].strip()
    last = re.sub(r";\s*Amtsgericht$", "", last)
    return re.sub(r"^Amtsgerichtsbezirk\s+", "", last).strip()


def named_first(title: str, place: str) -> bool:
    """Whether the title begins with the place: the book is the place's own.

    Otherwise the place is named later, usually as the municipality a village
    now belongs to (``Niederrimsingen, Breisach am Rhein FR; ...``).
    """
    head = re.split(r"[,;]", title or "", maxsplit=1)[0].strip().lower()
    return head == place.lower() or head.startswith(place.lower() + " ")


def split_signature(reference: str) -> tuple[str, str]:
    """(department, short signature) from ``Abt. Staatsarchiv Freiburg, L 10 Nr. 510``."""
    m = re.match(r"(?:Abt\.\s*)?(?P<dept>[^,]+),\s*(?P<sig>.+)$", reference or "")
    return (m.group("dept").strip(), m.group("sig").strip()) if m else ("", reference or "")


def signature_number(short: str) -> int:
    """The number after ``Nr.``, for ordering."""
    m = re.search(r"Nr\.\s*(\d+)", short or "")
    return int(m.group(1)) if m else 0


def book_row(doc: dict, place: str) -> dict:
    """One book from a DDB hit, shaped for ``labw_standesbuch``."""
    reference = first(doc.get("apd_reference_number"))
    department, short = split_signature(reference)
    title = first(doc.get("title"))
    begin, end = from_day_number(doc.get("begin_time")), from_day_number(doc.get("end_time"))
    row: dict[str, Any] = {
        "signature": short,
        "archive": f"{ARCHIVE}, Abt. {department}" if department else ARCHIVE,
        "title": title,
    }
    if begin and end:
        row["years"] = f"{begin.year}-{end.year}"
    row["confessions"] = confessions_of(title)
    if court := court_of(first(doc.get("apd_context"))):
        row["district_court"] = court
    row["place_named_first"] = named_first(title, place)
    match = re.fullmatch(r"labw-(\d)-(\d{1,10})", first(doc.get("provider_item_id")))
    if match:
        row["permalink"] = permalink(int(match.group(1)), int(match.group(2)))
        row["_scope"] = (int(match.group(1)), int(match.group(2)))
    row["ddb_id"] = first(doc.get("id"))
    row["_years"] = (begin.year if begin else 0, end.year if end else 9999)
    return row


def citation(book: Book, number: int, file: str) -> dict[str, str]:
    """How to cite one image: the archive, the signature, the image, the permalink."""
    archive = f"{ARCHIVE}, Abt. {book.department}" if book.department else ARCHIVE
    image = image_id(file)
    link = permalink(book.archive, book.scope, image) if image is not None else book.permalink
    return {
        "text": f"{archive}, {book.signature}, Bild {number}",
        "archive": archive,
        "signature": book.signature,
        "title": book.title,
        "image": f"Bild {number}",
        "permalink": link,
    }
