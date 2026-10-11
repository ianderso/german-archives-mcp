"""The Hessisches Landesarchiv's digitised civil registers: LAGIS's catalogue, Arcinsys's images.

The Personenstandsarchiv Hessen, part of the Hessisches Staatsarchiv Marburg,
keeps the secondary copies (Nebenregister) of every Standesamt in today's
Hesse from 1874/1876, in fonds HStAM 900 to 926, one per district, and has
put them online to 1900 (births), 1930 (marriages) and 1965 (deaths).

* **Finding a register: LAGIS.** The Landesgeschichtliches Informationssystem
  Hessen catalogues the digitised registers (118,206 entries) behind a keyless
  JSON API on ``www.lagis-hessen.de``. Its simple search,
  ``/de/api/gsearch/sn/hessische-geburten-ehe-sterberegister?suchbegriff=``,
  matches every word against the register's title and the places of its
  Standesamt district, so a village finds the registers of the Standesamt it
  belonged to. Each hit names the register (``Korbach,
  Geburtsnebenregister, 1880``) and its signature (``HStAM Bestand 922 Nr.
  6013``).
* **Reading a page: Arcinsys Hessen.** The signature autocompleter
  (``/arcinsys/queryItemSignatureSuggestions``) gives, for a fonds and number,
  Arcinsys's id for the unit; ``/arcinsys/mets?detailid=v<id>`` is the METS
  file Arcinsys hands the DFG-Viewer, listing the page images in order; the
  images are static JPEGs on ``digitalisate-he.arcinsys.de``. No session, no
  form state and no script is needed for any of it.

Observed 2026-10-11; see docs/API-NOTES.md.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from .client import ARCINSYS_HOST, HLA_IMAGE_HOST, LAGIS_HOST

#: LAGIS's simple search over the register catalogue.
LAGIS_SEARCH = f"https://{LAGIS_HOST}/de/api/gsearch/sn/hessische-geburten-ehe-sterberegister"

#: A register's short LAGIS address, which LAGIS gives for citing it.
LAGIS_PERMALINK = "https://lagis.hessen.de/resolve/de/pstr/{id}"

#: Arcinsys Hessen's base.
ARCINSYS = f"https://{ARCINSYS_HOST}/arcinsys"

#: The register types, as LAGIS titles them.
REGISTERS: dict[str, str] = {
    "birth": "Geburtsnebenregister",
    "marriage": "Heiratsnebenregister",
    "death": "Sterbenebenregister",
}

#: The Hessisches Landesarchiv's departments in Arcinsys: abbreviation to
#: (Arcinsys's archive id, name), as its autocompleter answered on 2026-10-11.
ARCHIVES: dict[str, tuple[int, str]] = {
    "HStAM": (84, "Hessisches Staatsarchiv Marburg"),
    "HHStAW": (47, "Hessisches Hauptstaatsarchiv Wiesbaden"),
    "HStAD": (1, "Hessisches Staatsarchiv Darmstadt"),
}

#: Most hits a LAGIS page lists: it caps a page at 25.
MAX_ROWS = 25

_TAG = re.compile(r"<[^>]+>")

#: A signature as LAGIS and a tool argument write it: ``HStAM Bestand 922 Nr.
#: 6013``, ``HStAM Best. 922 Nr. 6013``, ``HStAM 922 Nr. 6013``, ``HStAM, 922, 6013``.
_SIGNATURE = re.compile(
    r"(?P<archive>HStAM|HHStAW|HStAD)\s*,?\s*(?:Best(?:and)?\.?\s*)?(?P<fonds>\d{1,5})"
    r"\s*,?\s*(?:Nr\.?\s*)?(?P<nr>\d{1,7})",
    re.I,
)

#: A LAGIS title: ``Korbach, Geburtsnebenregister, 1880`` or
#: ``Affolterbach, Geburtsnebenregister (1876)``.
_TITLE = re.compile(r"^(?P<place>.+?),\s*(?P<kind>[^,(]+?)(?:,\s*|\s*\()(?P<years>[\d\s\-–/]+)\)?$")

#: A page image on Arcinsys Hessen's image server.
_IMAGE_PATH = re.compile(r"/[a-z]{2,10}/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*/\d{1,6}\.jpe?g")

#: Characters a place may contain.
_PLACE = re.compile(r"[\w .'()\-]{2,80}")


def plain(text: Any) -> str:
    """Markup removed, entities decoded, spaces collapsed."""
    if not isinstance(text, str):
        return ""
    return " ".join(html.unescape(_TAG.sub(" ", text)).split())


def valid_place(place: str) -> str | None:
    """A place argument, tidied, or None if it is not a plausible place name."""
    text = " ".join((place or "").split())
    return text if _PLACE.fullmatch(text) else None


def search_terms(place: str, register: str = "", year: int | None = None) -> str:
    """LAGIS's words: the place's words, the register type and the year; all must match."""
    words = [w for w in re.split(r"[\s()']+", place) if w.strip(".-")]
    if register:
        words.append(REGISTERS[register])
    if year is not None:
        words.append(str(year))
    return " ".join(words)


def search_url(terms: str, *, page: int, rows: int) -> str:
    """LAGIS's simple-search address; ``page`` counts from 1."""
    params = [("suchbegriff", terms), ("seite", str(page)), ("datensaetze", str(rows))]
    return f"{LAGIS_SEARCH}?{urlencode(params, quote_via=quote)}"


def lagis_permalink(lagis_id: str) -> str:
    """A register's short LAGIS address."""
    return LAGIS_PERMALINK.format(id=quote(lagis_id, safe="-"))


def parse_signature(text: str) -> tuple[str, str, int] | None:
    """(archive, fonds, number) from ``HStAM Bestand 922 Nr. 6013`` and the like, or None."""
    match = _SIGNATURE.fullmatch(" ".join((text or "").split()))
    if not match:
        return None
    archive = next(a for a in ARCHIVES if a.lower() == match.group("archive").lower())
    return archive, match.group("fonds"), int(match.group("nr"))


def signature(archive: str, fonds: str, number: int | str) -> str:
    """``HStAM 922 Nr. 6013``."""
    return f"{archive} {fonds} Nr. {number}"


def hit(doc: dict) -> dict:
    """One LAGIS hit, shaped to cite, to judge and to read with ``hessen_image``."""
    title = plain(doc.get("title"))
    out: dict[str, Any] = {"title": title}
    match = _TITLE.match(title)
    if match:
        out["standesamt"] = match.group("place").strip()
        kind = match.group("kind").strip()
        out["register"] = next((k for k, v in REGISTERS.items() if v == kind), kind)
        out["years"] = match.group("years").strip()
    elif location := plain(doc.get("location")):
        out["standesamt"] = location
    parsed = parse_signature(plain(doc.get("subTitle")))
    if parsed:
        archive, fonds, number = parsed
        out["signature"] = signature(archive, fonds, number)
        out["archive"] = ARCHIVES[archive][1]
    elif sub := plain(doc.get("subTitle")):
        out["signature"] = sub
    lagis_id = str(doc.get("id") or "")
    if re.fullmatch(r"[\w\-]{1,40}", lagis_id):
        out["lagis_id"] = lagis_id
        out["lagis_permalink"] = lagis_permalink(lagis_id)
    return out


def items_url(archive_id: int, fonds: str, number: int) -> str:
    """Arcinsys's autocompleter for a unit's signature, which answers with its id."""
    params = [
        ("archivId", str(archive_id)),
        ("bestandSignature", fonds),
        ("stueckSignature", str(number)),
    ]
    return f"{ARCINSYS}/queryItemSignatureSuggestions?{urlencode(params)}"


def unit_id(answer: Any, number: int) -> int | None:
    """Arcinsys's id for the unit numbered exactly ``number``, from the autocompleter's answer.

    The autocompleter matches by prefix (``10`` also suggests ``100``), so
    only an exact match counts.
    """
    rows = answer.get("stueckSignatureSuggestions") if isinstance(answer, dict) else None
    for row in rows or []:
        if not isinstance(row, dict) or str(row.get("selectValue", "")).strip() != str(number):
            continue
        key = str(row.get("selectKey", ""))
        if key.isdigit():
            return int(key)
    return None


def mets_url(unit: int) -> str:
    """The METS file Arcinsys hands the DFG-Viewer for a unit."""
    return f"{ARCINSYS}/mets?detailid=v{unit}"


def permalink(unit: int) -> str:
    """A unit's Arcinsys detail page, the address its METS file names as the record."""
    return f"{ARCINSYS}/detailAction?detailid=v{unit}"


def parse_item(text: str) -> tuple[str, int] | tuple[str, tuple[str, str, int]] | None:
    """What a ``hessen_image`` argument names: ``("id", unit)`` or ``("signature", (archive,
    fonds, number))``, or None.

    An Arcinsys address names the unit by ``detailid=v<id>``,
    ``archivalDescriptionId=<id>`` or ``mets?detailid=v<id>``; ``v<id>`` alone
    works too.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        parts = urlsplit(raw)
        if (parts.hostname or "").lower() != ARCINSYS_HOST:
            return None
        query = parse_qs(parts.query)
        for key in ("detailid", "archivalDescriptionId"):
            for value in query.get(key) or []:
                digits = value[1:] if value[:1] in ("v", "V") else value
                if digits.isdigit() and len(digits) <= 12:
                    return "id", int(digits)
        return None
    if re.fullmatch(r"[vV]\d{1,12}", raw):
        return "id", int(raw[1:])
    parsed = parse_signature(raw)
    return ("signature", parsed) if parsed else None


@dataclass
class Mets:
    """What ``hessen_image`` reads from a unit's METS file."""

    title: str
    shelf: str = ""
    owner: str = ""
    license: str = ""
    pages: list[str] = field(default_factory=list)

    @property
    def signature(self) -> str:
        """``HStAM 922 Nr. 6013`` from the shelf mark ``HStAM 922 6013``, or the mark itself."""
        parsed = parse_signature(self.shelf)
        return signature(*parsed) if parsed else self.shelf


def _local(tag: str) -> str:
    """A pattern for an element of any namespace prefix."""
    return rf"(?:\w+:)?{tag}"


def parse_mets(text: str) -> Mets | None:
    """A unit's title, shelf mark, owner, licence and page images in viewer order.

    Pages are the ``DEFAULT`` file group, ordered by the physical structure
    map's ``ORDER``; without a structure map, in file order. Arcinsys leaves
    out pages still under a protection period, so page *n* is the *n*th image
    shown, which can differ from the number in its file name.
    """
    body = text or ""
    if not re.search(r"<" + _local("mets") + r"\b", body):
        return None
    title = re.search(r"<" + _local("title") + r">(.*?)</", body, re.S)
    shelves = re.findall(r"<" + _local("shelfLocator") + r">(.*?)</", body, re.S)
    owner = re.search(r"<" + _local("owner") + r">(.*?)</", body, re.S)
    license_ = re.search(r"<" + _local("license") + r">(.*?)</", body, re.S)
    group = re.search(
        r"<" + _local("fileGrp") + r'\b[^>]*\bUSE="DEFAULT"[^>]*>(.*?)</' + _local("fileGrp") + ">",
        body,
        re.S,
    )
    if not group:
        return None
    files: dict[str, str] = {}
    order: list[str] = []
    for fid, href in re.findall(
        r"<"
        + _local("file")
        + r'\b[^>]*\bID="([^"]+)"[^>]*>\s*<'
        + _local("FLocat")
        + r'\b[^>]*\bhref="([^"]+)"',
        group.group(1),
        re.S,
    ):
        files[fid] = html.unescape(href)
        order.append(fid)
    physical = re.search(
        r"<"
        + _local("structMap")
        + r'\b[^>]*TYPE="PHYSICAL"[^>]*>(.*?)</'
        + _local("structMap")
        + ">",
        body,
        re.S,
    )
    pages: list[str] = []
    if physical:
        divs = []
        for tag, inner in re.findall(
            r"(<" + _local("div") + r'\b(?=[^>]*\bTYPE="page")[^>]*>)(.*?)</' + _local("div") + ">",
            physical.group(1),
            re.S,
        ):
            position = re.search(r'\bORDER="(\d+)"', tag)
            fid = next((f for f in re.findall(r'FILEID="([^"]+)"', inner) if f in files), None)
            if fid and position:
                divs.append((int(position.group(1)), files[fid]))
        pages = [href for _, href in sorted(divs, key=lambda d: d[0])]
    if not pages:
        pages = [files[fid] for fid in order]
    return Mets(
        title=plain(title.group(1)) if title else "",
        shelf=plain(shelves[0]) if shelves else "",
        owner=plain(owner.group(1)) if owner else "",
        license=plain(license_.group(1)) if license_ else "",
        pages=pages,
    )


def readable_image(url: str) -> bool:
    """Whether an address from a METS file is a page image on Arcinsys Hessen's image server."""
    parts = urlsplit(url or "")
    return (
        parts.scheme == "https"
        and (parts.hostname or "").lower() == HLA_IMAGE_HOST
        and ".." not in parts.path
        and not parts.query
        and not parts.fragment
        and bool(_IMAGE_PATH.fullmatch(parts.path))
    )


def citation(mets: Mets, page: int, unit: int, image: str) -> dict[str, str]:
    """How to cite one page: the archive, the signature, the image, the permalink."""
    archive = mets.owner or "Hessisches Landesarchiv"
    file_name = image.rsplit("/", 1)[-1]
    return {
        "text": f"{archive}, {mets.signature} ({mets.title}), Bild {page}",
        "archive": archive,
        "signature": mets.signature,
        "image": f"Bild {page}",
        "file": file_name,
        "permalink": permalink(unit),
    }
