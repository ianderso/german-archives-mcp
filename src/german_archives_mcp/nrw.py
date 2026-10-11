"""The Archive in NRW portal and the Landesarchiv NRW's digitised registers.

The portal (``www.archive.nrw.de``) holds the finding aids of the Landesarchiv
Nordrhein-Westfalen and of some four hundred other archives in the state. Its
search page is built on a keyless JSON service, ``/sufservice/api/search``,
which answers a keyword with hits that carry the archive, the signature, the
dates, the fonds, a permalink and, for a digitised unit, a DFG-Viewer link
whose ``tx_dlf[id]`` is the unit's METS file.

The Landesarchiv's own digitised units (above all the civil registers,
Personenstandsregister, of the Rhineland from 1798 and of Westphalia and
Lippe, with some church-book duplicates, as far as the protection periods
allow) have their METS files and
page images on ``www.landesarchiv-nrw.de``: the METS lists each page as a
JPEG in its ``DEFAULT`` file group, in the order of its physical structure
map. Page *n* is the *n*th entry. Other archives' METS files are on their own
servers and are returned as links only.

Observed 2026-10-11; see docs/API-NOTES.md.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from .client import NRW_IMAGE_HOST, NRW_PORTAL_HOST

#: The portal's base.
PORTAL = f"https://{NRW_PORTAL_HOST}"

#: The search service the portal's own search page calls.
SEARCH = f"{PORTAL}/sufservice/api/search"

#: A unit's permalink, from the id in its METS file.
PERMALINK = PORTAL + "/ms/search?link=VERZEICHUNGSEINHEIT-Vz_{uuid}"

#: The Landesarchiv's three departments, as the portal numbers them (its
#: ``mandant``), and as it names them.
ARCHIVES: dict[str, tuple[str, str]] = {
    "rheinland": ("185", "Landesarchiv NRW Abteilung Rheinland"),
    "westfalen": ("1", "Landesarchiv NRW Abteilung Westfalen"),
    "ostwestfalen-lippe": ("10003", "Landesarchiv NRW Abteilung Ostwestfalen-Lippe"),
}

#: Longest keyword sent.
MAX_QUERY_CHARS = 200

#: A METS address on the Landesarchiv's image server.
_METS_PATH = re.compile(
    r"/digitalisate/(?P<path>[A-Za-z0-9_~.\-]+(?:/[A-Za-z0-9_~.\-]+)*)/mets\.xml"
)

#: A bare METS path as a tool argument may give it: ``Abt_Rheinland/PA_2104/~002/00267``.
_SHORT_PATH = re.compile(r"(?:Abt_[A-Za-z\-]+)(?:/[A-Za-z0-9_~.\-]+)+")

#: A page image on the Landesarchiv's image server.
_IMAGE_PATH = re.compile(r"/data\d{0,3}/[A-Za-z0-9_~.\-]+(?:/[A-Za-z0-9_~.\-]+)*\.jpe?g")

#: A METS title: ``Abteilung Rheinland, PA 2104 (Zivilstandsregister ...), Nr. 267``.
_TITLE = re.compile(
    r"^(?P<dept>Abteilung [^,]+),\s*(?P<fonds>[^(]+?)\s*\((?P<ftitle>.*)\),\s*Nr\.\s*(?P<nr>.+)$"
)

_TAG = re.compile(r"<[^>]+>")


def plain(text: Any) -> str:
    """Markup removed (the search wraps matches in ``<mark>``) and entities decoded."""
    if not isinstance(text, str):
        return ""
    return " ".join(html.unescape(_TAG.sub(" ", text)).split())


def clean_query(text: str) -> str:
    """Search words as one line of printable text."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in text or "").split())


def search_url(
    *,
    keyword: str,
    archive: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    has_images: bool = True,
    page: int = 0,
    size: int = 20,
) -> str:
    """The search address. ``page`` counts from 0, as the service does."""
    params: list[tuple[str, str]] = [("keyword", keyword)]
    if has_images:
        params.append(("hasDigitalisat", "true"))
    if archive:
        params.append(("archive", ARCHIVES[archive][0]))
    if year_from is not None:
        params.append(("laufzeitVon", str(year_from)))
    if year_to is not None:
        params.append(("laufzeitBis", str(year_to)))
    params += [("size", str(size)), ("page", str(page))]
    return f"{SEARCH}?{urlencode(params, quote_via=quote)}"


def mets_url(path: str) -> str:
    """The METS address for a path below ``/digitalisate/``."""
    return f"https://{NRW_IMAGE_HOST}/digitalisate/{path}/mets.xml"


def mets_from_viewer(link: str) -> str:
    """The METS address inside a DFG-Viewer link, or the link itself if it names none."""
    query = parse_qs(urlsplit(link or "").query)
    for key in ("tx_dlf[id]", "set[mets]"):
        if query.get(key):
            return query[key][0]
    return link or ""


def readable_mets(address: str) -> str | None:
    """The address normalised if it is a METS file on the Landesarchiv's server, else None."""
    parts = urlsplit((address or "").strip())
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() != NRW_IMAGE_HOST:
        return None
    if ".." in parts.path or parts.query or parts.fragment:
        return None
    match = _METS_PATH.fullmatch(parts.path)
    return mets_url(match.group("path")) if match else None


def parse_item(text: str) -> str | None:
    """The METS address an ``nrw_image`` argument names: a METS address, a DFG-Viewer link
    holding one, or the path below ``/digitalisate/``."""
    raw = (text or "").strip()
    if not raw:
        return None
    if "dfg-viewer" in raw:
        raw = mets_from_viewer(raw)
    if raw.startswith(("http://", "https://")):
        return readable_mets(raw)
    path = raw.strip("/").removesuffix("/mets.xml")
    if _SHORT_PATH.fullmatch(path) and ".." not in path:
        return mets_url(path)
    return None


def readable_image(url: str) -> bool:
    """Whether an address from a METS file is a page image on the Landesarchiv's server."""
    parts = urlsplit(url or "")
    return (
        parts.scheme == "https"
        and (parts.hostname or "").lower() == NRW_IMAGE_HOST
        and ".." not in parts.path
        and not parts.query
        and bool(_IMAGE_PATH.fullmatch(parts.path))
    )


def hit(doc: dict) -> dict:
    """One search hit, shaped to cite and to judge."""
    out: dict[str, Any] = {"title": plain(doc.get("title"))}
    if dates := plain(doc.get("laufzeit")):
        out["dates"] = dates
    if archive := plain(doc.get("archivName")):
        out["institution"] = archive
    number = plain(doc.get("signatur"))
    fonds = plain(doc.get("bestandSignature"))
    if number:
        out["signature"] = f"{fonds} Nr. {number}" if fonds else number
    if fonds_title := plain(doc.get("bestandTitle")):
        out["fonds"] = f"{fonds} {fonds_title}".strip()
    kind = doc.get("objectTyp")
    if isinstance(kind, dict) and (label := plain(kind.get("displayValue"))):
        out["level"] = label
    if abstract := doc.get("textAbstract"):
        if isinstance(abstract, list):
            abstract = " ".join(a for a in abstract if isinstance(a, str))
        if text := plain(str(abstract).replace("#", " ")):
            out["abstract"] = text[:300]
    viewers = [v for v in doc.get("disitalisat") or [] if isinstance(v, str)]
    if viewers:
        out["viewer"] = viewers[0]
        mets = mets_from_viewer(viewers[0])
        readable = readable_mets(mets)
        out["mets"] = readable or mets
        out["readable_by_nrw_image"] = readable is not None
    if restriction := plain(doc.get("accessrestrict")):
        out["access_note"] = restriction
    if permalink := doc.get("permalink"):
        out["permalink"] = str(permalink).replace("http://", "https://", 1)
    return out


@dataclass
class Mets:
    """What ``nrw_image`` reads from one unit's METS file."""

    title: str
    pages: list[str] = field(default_factory=list)
    permalink: str = ""
    urn: str = ""
    license: str = ""
    license_url: str = ""
    owner: str = ""

    @property
    def parts(self) -> dict[str, str]:
        """The department, fonds, fonds title and number, read from the title."""
        match = _TITLE.match(self.title)
        return match.groupdict() if match else {}

    @property
    def signature(self) -> str:
        """``PA 2104 Nr. 267``, or the title if it has another shape."""
        parts = self.parts
        return f"{parts['fonds']} Nr. {parts['nr']}" if parts else self.title

    @property
    def archive(self) -> str:
        """``Landesarchiv NRW Abteilung Rheinland``."""
        parts = self.parts
        owner = self.owner or "Landesarchiv NRW"
        return f"{owner} {parts['dept']}" if parts else owner


def _attr(tag: str, name: str) -> str:
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return html.unescape(match.group(1)) if match else ""


def parse_mets(text: str) -> Mets | None:
    """A unit's title, page images in order, permalink and licence, from its METS file.

    Page images are the ``DEFAULT`` file group, ordered by the physical
    structure map's ``ORDER``; without a structure map, in file order.
    """
    if "<mets:mets" not in (text or ""):
        return None
    title_match = re.search(r"<mods:title>(.*?)</mods:title>", text, re.S)
    title = plain(title_match.group(1)) if title_match else ""
    group = re.search(r'<mets:fileGrp\b[^>]*\bUSE="DEFAULT"[^>]*>(.*?)</mets:fileGrp>', text, re.S)
    if not group:
        return None
    files: dict[str, str] = {}
    order: list[str] = []
    for file_tag, body in re.findall(
        r"(<mets:file\b[^>]*>)(.*?)</mets:file>", group.group(1), re.S
    ):
        fid = _attr(file_tag, "ID")
        loc = re.search(r"<mets:FLocat\b[^>]*>", body)
        href = _attr(loc.group(0), "xlink:href") if loc else ""
        if fid and href:
            files[fid] = href
            order.append(fid)
    physical = re.search(
        r'<mets:structMap\b[^>]*TYPE="PHYSICAL"[^>]*>(.*?)</mets:structMap>', text, re.S
    )
    pages: list[str] = []
    if physical:
        divs = []
        for div_tag, body in re.findall(
            r'(<mets:div\b[^>]*TYPE="page"[^>]*>)(.*?)</mets:div>', physical.group(1), re.S
        ):
            try:
                position = int(_attr(div_tag, "ORDER"))
            except ValueError:
                continue
            fid = next((f for f in re.findall(r'FILEID="([^"]+)"', body) if f in files), None)
            if fid:
                divs.append((position, files[fid]))
        pages = [href for _, href in sorted(divs)]
    if not pages:
        pages = [files[fid] for fid in order]
    dockey = re.search(r'<mods:identifier type="VERA dockey">\s*Vz\s+([0-9A-Fa-f\-]{36})', text)
    urn = re.search(r'<mods:identifier type="urn">\s*([^<\s]+)', text)
    access = re.search(r"(<mods:accessCondition\b[^>]*>)(.*?)</mods:accessCondition>", text, re.S)
    owner = re.search(r"<dv:owner>(.*?)</dv:owner>", text, re.S)
    return Mets(
        title=title,
        pages=pages,
        permalink=PERMALINK.format(uuid=dockey.group(1)) if dockey else "",
        urn=urn.group(1) if urn else "",
        license=plain(access.group(2)) if access else "",
        license_url=_attr(access.group(1), "href") if access else "",
        owner=plain(owner.group(1)) if owner else "",
    )


def citation(mets: Mets, number: int, mets_address: str) -> dict[str, str]:
    """How to cite one page: the archive, the signature, the image, the permalink."""
    parts = mets.parts
    return {
        "text": f"{mets.archive}, {mets.signature}, Bild {number}",
        "archive": mets.archive,
        "signature": mets.signature,
        "fonds": f"{parts['fonds']} {parts['ftitle']}" if parts else "",
        "image": f"Bild {number}",
        "permalink": mets.permalink or mets_address,
        "urn": mets.urn,
    }
