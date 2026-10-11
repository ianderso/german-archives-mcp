"""APERTUS, the Landesarchivverwaltung Rheinland-Pfalz's virtual reading room.

The Personenstandsarchiv Rheinland-Pfalz, part of the Landeshauptarchiv
Koblenz, has put the civil registers of the state's north online in APERTUS
(``apertus.rlp.de``): Best. 657,001 onward, one fonds per Standesamt or
Bürgermeisterei, from 1798: about 18,500 birth, 19,700 marriage and 21,000
death registers have images, some whole and some only their name index (the
archive counts 32,000 whole registers and 28,000 indexes, March 2026).
APERTUS is a PHP application whose
pages are HTML fragments fetched by form posts; it answered these without a
cookie or a token (2026-10-11):

* ``queryOneExt.php`` lists units: a keyword query (words joined with
  ``+AND+``, as the site's own form does), an optional fonds and number, a
  year range, a digitised-only flag, an offset and a page size. Each unit
  comes with its GUID, signature (``Best. 657,349 Nr. 4``), title and dates.
* ``vz_php.php`` describes one unit by its GUID and, as a side effect, builds
  the unit's images as one PDF of the whole volume under ``/Bild/``, which
  the archive deletes again within minutes. A page is reachable only inside
  that PDF.

So the server finds units with the first, and reads a page by opening the
unit, downloading its PDF once, and keeping it on disk for a few days (see
:mod:`german_archives_mcp.volumes`).

Observed 2026-10-11; see docs/API-NOTES.md.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .client import APERTUS_HOST

#: The site.
BASE = f"https://{APERTUS_HOST}"

#: The unit search.
SEARCH = f"{BASE}/queryOneExt.php"

#: A unit's description, which also builds its PDF.
UNIT = f"{BASE}/vz_php.php"

#: A unit's permalink, as the site writes it.
PERMALINK = BASE + "/index.php?PLINK=1&ID={guid}"

#: The archive that holds the registers, as the site names it.
ARCHIVE = "Personenstandsarchiv Rheinland-Pfalz"

#: How a citation names the holder.
HOLDER = "Landesarchivverwaltung Rheinland-Pfalz, Landeshauptarchiv Koblenz"

#: The register types, as APERTUS titles them.
REGISTERS: dict[str, str] = {
    "birth": "Geburtsregister",
    "marriage": "Heiratsregister",
    "death": "Sterberegister",
}

#: Longest place argument, in characters.
MAX_PLACE_CHARS = 80

#: Most units a search page lists.
MAX_ROWS = 50

_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

#: A fonds of the Personenstandsarchiv: ``657,349``.
_FONDS = re.compile(r"\d{3},\d{3}")

#: A signature as a tool argument may give it: ``Best. 657,349 Nr. 4``,
#: ``657,349 Nr. 4``, ``Bestand 657,349 Nummer 4``, ``LHA Ko Best. 657,349 Nr. 4``.
_SIGNATURE = re.compile(
    r"(?:(?:LHA\s*Ko|LHAKo|PStA)\.?\s*,?\s*)?(?:Best(?:and)?\.?\s*)?(?P<fonds>\d{3},\d{3})\s*,?\s*"
    r"(?:Nr\.?|Nummer)?\s*(?P<nr>\d{1,6})",
    re.I,
)

#: The PDF path a unit's description names.
_PDF_PATH = re.compile(r"/Bild/[A-Za-z0-9_,.\-]{1,120}\.pdf")

_TAG = re.compile(r"<[^>]+>")

#: Characters a place may contain: letters, digits, spaces and a few marks.
_PLACE = re.compile(r"[\w .'()\-]{2,80}")


def plain(text: Any) -> str:
    """Markup removed, entities decoded, spaces collapsed."""
    if not isinstance(text, str):
        return ""
    return " ".join(html.unescape(_TAG.sub(" ", text.replace("</br>", " "))).split())


def valid_place(place: str) -> str | None:
    """A place argument, tidied, or None if it is not a plausible place name."""
    text = " ".join((place or "").split())
    return text if _PLACE.fullmatch(text) else None


def query(place: str, register: str = "") -> str:
    """The query APERTUS's own form makes of a place and a register: words joined by ``+AND+``.

    Parentheses and apostrophes are dropped, so ``St. Johann (bei Mayen)``
    becomes ``St.+AND+Johann+AND+bei+AND+Mayen``.
    """
    words = [w for w in re.split(r"[\s()']+", place) if w.strip(".-")]
    if register:
        words.insert(0, REGISTERS[register])
    return "+AND+".join(words)


def search_form(
    q: str, *, year_from: int | None, year_to: int | None, start: int, rows: int
) -> dict[str, str]:
    """The form ``queryOneExt.php`` takes for a keyword search of digitised units."""
    return {
        "archiv": "PStA",
        "panel": "VE",
        "panelID": "1",
        "query": q,
        "bestand": "",
        "nummer": "",
        "unum": "",
        "zusatz": "",
        "range": "" if year_from is None else str(year_from),
        "range2": "" if year_to is None else str(year_to),
        "doc": "TRUE",
        "start": str(start),
        "rows": str(rows),
        "thema": "",
    }


def signature_form(fonds: str, number: int) -> dict[str, str]:
    """The form ``queryOneExt.php`` takes to find one unit by its signature."""
    form = search_form("", year_from=None, year_to=None, start=0, rows=10)
    form.update({"bestand": fonds, "nummer": str(number)})
    return form


def unit_form(guid: str) -> dict[str, str]:
    """The form ``vz_php.php`` takes to describe one unit (and build its PDF)."""
    return {"GUID": guid, "FLAG": "2", "NR": "0", "NRMAX": "0"}


def permalink(guid: str) -> str:
    """A unit's permalink."""
    return PERMALINK.format(guid=guid)


def signature(fonds: str, number: str) -> str:
    """``Best. 657,349 Nr. 4``."""
    return f"Best. {fonds} Nr. {number}"


def parse_signature(text: str) -> tuple[str, int] | None:
    """(fonds, number) from a signature such as ``Best. 657,349 Nr. 4``, or None."""
    match = _SIGNATURE.fullmatch(" ".join((text or "").split()))
    if not match:
        return None
    return match.group("fonds"), int(match.group("nr"))


def parse_item(text: str) -> tuple[str, str] | tuple[str, tuple[str, int]] | None:
    """What an ``rlp_image`` argument names: ``("guid", guid)``, ``("signature", (fonds,
    number))``, or None.

    A GUID may come bare or inside the permalink.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        parts = urlsplit(raw)
        if (parts.hostname or "").lower() != APERTUS_HOST:
            return None
        ids = parse_qs(parts.query).get("ID") or []
        if ids and _GUID.fullmatch(ids[0]):
            return "guid", ids[0].lower()
        return None
    if _GUID.fullmatch(raw):
        return "guid", raw.lower()
    parsed = parse_signature(raw)
    return ("signature", parsed) if parsed else None


def register_of(title: str) -> str:
    """``birth``, ``marriage``, ``death`` or ``other``, from a unit's title."""
    for key, word in REGISTERS.items():
        if title.startswith(word):
            return key
    return "other"


def office_of(title: str) -> str:
    """The Standesamt or Bürgermeisterei a register title names: what follows ``der``/``des``."""
    match = re.search(r"\b(?:der|des)\s+(.+)$", title)
    return match.group(1).strip() if match else ""


def parse_units(text: str) -> tuple[int, list[dict]] | None:
    """(total, units) from a ``queryOneExt.php`` answer, or None if it has another shape.

    A blank answer (a bare line break) is APERTUS's way of saying it found
    nothing.
    """
    body = text or ""
    if not body.strip():
        return 0, []
    header = re.search(r"<b>Bestand[^<]*</b>\s*\((?:\d+-)?\d+\s+von\s+(\d+)\)", body)
    if header is None:
        return None
    units = []
    for block in body.split("<div class='thead'>")[1:]:
        guid = re.search(r'value="([0-9a-fA-F-]{36})"', block)
        head = re.search(r"<div class='tclickhead'[^>]*>(.*?)</div>", block, re.S)
        if not guid or not head or not _GUID.fullmatch(guid.group(1)):
            continue
        head_text = head.group(1)
        sig = re.search(r"Best\.\s*(\d{3},\d{3})\s+Nr\.\s*([^<\s][^<]*)", head_text)
        lines = [plain(x) for x in re.findall(r"<div class='simplelist'[^>]*>(.*?)</div>", block)]
        dates = re.search(r"<div class=1>(.*?)</div>", block, re.S)
        kind = re.search(r"<span[^>]*>(.*?)</span>", head_text)
        archive = plain(head_text.split("<span", 1)[0])
        title = lines[0] if lines else ""
        unit: dict[str, Any] = {
            "guid": guid.group(1).lower(),
            "signature": signature(sig.group(1), sig.group(2).strip()) if sig else "",
            "fonds": sig.group(1) if sig else "",
            "number": sig.group(2).strip() if sig else "",
            "title": title,
            "years": lines[1] if len(lines) > 1 else "",
            "dates": plain(dates.group(1)) if dates else "",
            "register": register_of(title),
            "office": office_of(title),
            "archive": archive or ARCHIVE,
            "kind": plain(kind.group(1)) if kind else "",
            "has_images": "class='listimage'" in block,
            "permalink": permalink(guid.group(1).lower()),
        }
        units.append(unit)
    return int(header.group(1)), units


@dataclass
class Unit:
    """What ``vz_php.php`` says of one unit."""

    guid: str
    fonds: str
    number: str
    title: str
    years: str = ""
    dates: str = ""
    fonds_title: str = ""
    archive: str = ARCHIVE
    pdf_path: str = ""
    details: dict[str, str] = field(default_factory=dict)

    @property
    def signature(self) -> str:
        """``Best. 657,349 Nr. 4``."""
        return signature(self.fonds, self.number)

    @property
    def permalink(self) -> str:
        """The unit's permalink."""
        return permalink(self.guid)

    def as_dict(self) -> dict[str, Any]:
        """The unit as stored beside its PDF."""
        return {
            "guid": self.guid,
            "fonds": self.fonds,
            "number": self.number,
            "title": self.title,
            "years": self.years,
            "dates": self.dates,
            "fonds_title": self.fonds_title,
            "archive": self.archive,
            "pdf_path": self.pdf_path,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Unit:
        """A unit stored by :meth:`as_dict`."""
        return cls(
            guid=str(data.get("guid", "")),
            fonds=str(data.get("fonds", "")),
            number=str(data.get("number", "")),
            title=str(data.get("title", "")),
            years=str(data.get("years", "")),
            dates=str(data.get("dates", "")),
            fonds_title=str(data.get("fonds_title", "")),
            archive=str(data.get("archive", ARCHIVE)),
            pdf_path=str(data.get("pdf_path", "")),
            details={str(k): str(v) for k, v in (data.get("details") or {}).items()},
        )


def parse_unit(text: str, guid: str) -> Unit | None:
    """A unit's signature, title, dates, notes and PDF path from ``vz_php.php``, or None.

    The PDF path is kept only if it has the shape the archive uses
    (``/Bild/PStA_657,349_4.pdf``): it becomes a request, so nothing else may.
    """
    body = text or ""
    sig = re.search(r"Bestand\s+(\d{3},\d{3})\s+Nummer\s+(\S[^<]*)</p>", body)
    if sig is None:
        return None
    title_match = re.search(r"<div class='titel[^']*'[^>]*>(.*?)</div>", body, re.S)
    title_parts = (
        [plain(p) for p in re.split(r"</br>|<br\s*/?>", title_match.group(1))]
        if title_match
        else []
    )
    dates = re.search(r"<div class=tnorm>(.*?)</div>", body, re.S)
    pdf = re.search(r"<embed class='pdfimage' src='([^']*)'", body)
    pdf_path = pdf.group(1) if pdf else ""
    if pdf_path and (not _PDF_PATH.fullmatch(pdf_path) or ".." in pdf_path):
        pdf_path = ""
    details = {
        plain(k): plain(v)
        for k, v in re.findall(
            r"<div class='td1'[^>]*>(.*?)</div><div class='td2'>(.*?)</div>", body, re.S
        )
    }
    fonds_title = re.search(r"<b>Bestand\s+\d{3},\d{3}\s*</b>([^<]*)", body)
    archive = details.pop("Lagerort", "") or ARCHIVE
    return Unit(
        guid=guid,
        fonds=sig.group(1),
        number=sig.group(2).strip(),
        title=title_parts[0] if title_parts else "",
        years=" ".join(p for p in title_parts[1:] if p),
        dates=plain(dates.group(1)) if dates else "",
        fonds_title=plain(fonds_title.group(1)) if fonds_title else "",
        archive=archive,
        pdf_path=pdf_path,
        details=details,
    )


def pdf_url(unit: Unit) -> str:
    """The address of a unit's PDF, from the path its description named."""
    return BASE + unit.pdf_path


def citation(unit: Unit, page: int) -> dict[str, str]:
    """How to cite one page: the archive, the signature, the PDF page, the permalink."""
    return {
        "text": f"{HOLDER}, {unit.signature} ({unit.title}"
        + (f", {unit.years}" if unit.years else "")
        + f"), PDF page {page}",
        "archive": f"{HOLDER} ({unit.archive})",
        "signature": unit.signature,
        "short": f"LHA Ko {unit.signature}",
        "fonds": f"Best. {unit.fonds} {unit.fonds_title}".strip(),
        "page": f"PDF page {page}",
        "permalink": unit.permalink,
    }
