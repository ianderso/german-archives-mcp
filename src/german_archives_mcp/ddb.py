"""The Deutsche Digitale Bibliothek's version 2 API: building requests, shaping answers.

The search is the DDB's own Apache Solr index, reached keylessly at
``/2/search/index/search/select``; an entry is read at ``/2/items/{id}``,
its place in the fonds at ``/2/items/{id}/parents``, and what lies below it at
``/2/items/{id}/children``. See docs/API-NOTES.md for what was observed.

Archival entries are finding-aid entries written by the holding archive and
delivered to the DDB (and so to Archivportal-D, its archive portal). The
signature (``apd_reference_number``), the context path (``apd_context``) and
the dates are the archive's own; the DDB adds ids and facets.
"""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Any
from urllib.parse import quote, urlencode

from .client import DDB_HOST

#: The API's base.
API = f"https://{DDB_HOST}/2"

#: The Solr search route.
SEARCH = f"{API}/search/index/search/select"

#: Public pages for an entry.
DDB_ITEM_URL = "https://www.deutsche-digitale-bibliothek.de/item/{id}"
ARCHIVPORTAL_ITEM_URL = "https://www.archivportal-d.de/item/{id}"

#: Fields a search asks for: enough to cite and to judge, nothing more.
SEARCH_FIELDS = (
    "id,title,dataprovider_fct,provider,apd_reference_number,apd_context,"
    "apd_level_of_description,begin_time,end_time,digitalisat,objecttype,"
    "sector_fct,provider_item_id"
)

#: Sectors, as the DDB codes them.
SECTORS = {
    "archive": "sec_01",
    "library": "sec_02",
    "monument": "sec_03",
    "research": "sec_04",
    "media": "sec_05",
    "museum": "sec_06",
    "other": "sec_07",
}
SECTOR_NAMES = {code: name for name, code in SECTORS.items()}

#: Levels of description in an archive's finding aid, as the DDB codes them
#: (observed on Archivportal-D entries, 2026-10-11).
LEVELS = {
    "htype_030": "fonds (Bestand)",
    "htype_031": "series (Gliederung)",
    "htype_032": "subseries",
    "htype_033": "file group",
    "htype_034": "unit (Verzeichnungseinheit)",
    "htype_035": "item within a unit",
    "htype_036": "item within a unit",
    "htype_037": "group of fonds (Tektonik)",
    "Tektonik_collection": "the archive's holdings overview (Tektonik)",
    "institution": "institution",
}

#: A DDB id: 32 characters of base32.
_ID = re.compile(r"[A-Z2-7]{32}")

#: Solr's syntax characters a query may not use: no fields, ranges, local
#: parameters, boosts or regular expressions. Quotes, parentheses, * and ?,
#: AND, OR, NOT, + and - keep their meaning.
_QUERY_SPECIAL = re.compile(r"([\\:/\[\]{}^~!])")

#: Longest query sent.
MAX_QUERY_CHARS = 300


def day_number(day: date) -> int:
    """The DDB's day count for a date, as its ``begin_time``/``end_time`` hold it.

    Observed 2026-10-11: 1847-01-01 is 674239, which is Python's ordinal plus one.
    """
    return day.toordinal() + 1


def from_day_number(value: Any) -> date | None:
    """The date a DDB day count stands for, or None if it is not one."""
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, int) or value < 2:
        return None
    try:
        return date.fromordinal(value - 1)
    except (ValueError, OverflowError):
        return None


def item_id(raw: str) -> str | None:
    """A DDB id from an id or an entry's address on the DDB or Archivportal-D."""
    text = (raw or "").strip()
    if _ID.fullmatch(text):
        return text
    match = re.search(
        r"(?:deutsche-digitale-bibliothek\.de|archivportal-d\.de)/(?:2/)?items?/([A-Z2-7]{32})",
        text,
    )
    return match.group(1) if match else None


def escape_query(text: str) -> str:
    """User words made safe for the Solr query: syntax characters escaped."""
    clean = " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())
    return _QUERY_SPECIAL.sub(r"\\\1", clean)


def escape_term(text: str) -> str:
    """A literal for a Solr string field: every character but letters and digits escaped."""
    return "".join(ch if ch.isalnum() else "\\" + ch for ch in text)


def search_url(
    *,
    query: str,
    filters: list[str],
    start: int,
    rows: int,
    fields: str = SEARCH_FIELDS,
    sort: str = "",
) -> str:
    """The search address for a query, its filters and a page."""
    params: list[tuple[str, str]] = [("q", query or "*:*")]
    params += [("fq", f) for f in filters]
    params += [("fl", fields), ("start", str(start)), ("rows", str(rows))]
    if sort:
        params.append(("sort", sort))
    return f"{SEARCH}?{urlencode(params, quote_via=quote)}"


def year_filters(year_from: int | None, year_to: int | None) -> list[str]:
    """Filters keeping entries whose dates overlap the years given."""
    out = []
    if year_to is not None:
        out.append(f"begin_time:[* TO {day_number(date(year_to, 12, 31))}]")
    if year_from is not None:
        out.append(f"end_time:[{day_number(date(year_from, 1, 1))} TO *]")
    return out


def first(value: Any) -> str:
    """The first string of a Solr value, which may be a list."""
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, str) and v.strip()), "")
    return value.strip() if isinstance(value, str) else ""


def years_of(doc: dict) -> str:
    """An entry's date range as years: ``1847-1870``, or one year, or ''."""
    begin, end = from_day_number(doc.get("begin_time")), from_day_number(doc.get("end_time"))
    if begin and end:
        return str(begin.year) if begin.year == end.year else f"{begin.year}-{end.year}"
    return str((begin or end).year) if (begin or end) else ""


def holder_of(doc: dict) -> str:
    """The holding institution of a search hit.

    ``dataprovider_fct`` names the holder; ``provider`` may also name an
    aggregator ("Archive in NRW") or a parent body, in no fixed order.
    """
    return first(doc.get("dataprovider_fct")) or first(doc.get("provider"))


def labw_scope(doc_or_id: Any) -> tuple[int, int] | None:
    """(archive, scope id) from a Landesarchiv entry's ``provider_item_id``, e.g. labw-5-475861."""
    raw = doc_or_id.get("provider_item_id") if isinstance(doc_or_id, dict) else doc_or_id
    match = re.fullmatch(r"labw-(\d)-(\d{1,10})", first(raw) if raw else "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def hit(doc: dict) -> dict:
    """One search hit, shaped to cite and to judge."""
    did = first(doc.get("id"))
    sector = first(doc.get("sector_fct"))
    out: dict[str, Any] = {"id": did, "title": clip(first(doc.get("title")), 300)}
    if holder := holder_of(doc):
        out["institution"] = holder
    if signature := first(doc.get("apd_reference_number")):
        out["signature"] = signature
    if years := years_of(doc):
        out["dates"] = years
    if context := first(doc.get("apd_context")):
        out["context"] = clip(context, 300)
    if level := first(doc.get("apd_level_of_description")):
        out["level"] = LEVELS.get(level, level)
    if kind := first(doc.get("objecttype")):
        out["kind"] = kind
    out["has_images"] = first(doc.get("digitalisat")) == "true"
    out["ddb_url"] = DDB_ITEM_URL.format(id=did)
    if sector == "sec_01":
        out["archivportal_url"] = ARCHIVPORTAL_ITEM_URL.format(id=did)
    return out


# --------------------------------------------------------------------------- #
# Reading one entry
# --------------------------------------------------------------------------- #
_TAG = re.compile(r"<[^>]+>")


def plain(text: Any) -> str:
    """Markup removed and entities decoded: the DDB passes some values as HTML."""
    if not isinstance(text, str):
        return ""
    return " ".join(html.unescape(_TAG.sub(" ", text)).split())


def clip(text: str, limit: int) -> str:
    """Text cut to ``limit`` characters at a word boundary, marked when cut."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] if " " in text[:limit] else text[:limit]
    return cut.rstrip() + " ..."


def display_fields(aip: dict) -> dict[str, str]:
    """The entry's fields as the DDB displays them: {German label: value}."""
    out: dict[str, str] = {}
    view = (aip.get("view") or {}).get("item") or {}
    for group in view.get("fields") or []:
        if not isinstance(group, dict) or group.get("usage") != "display":
            continue
        for field in group.get("field") or []:
            name = plain(field.get("name"))
            values = [plain(v.get("content")) for v in field.get("value") or [] if v]
            value = " | ".join(v for v in values if v)
            if name and value:
                key = name if name not in out else f"{name} (2)"
                out[key] = clip(value, 2000)
    return out


def _edm(aip: dict) -> dict:
    return ((aip.get("edm") or {}).get("RDF")) or {}


def _resource(node: Any) -> str:
    return node.get("resource") or "" if isinstance(node, dict) else ""


def holder_page(aip: dict) -> str:
    """The holding institution's own page for the entry, if the record names one."""
    view = (aip.get("view") or {}).get("item") or {}
    origin = view.get("origin")
    if isinstance(origin, str) and origin.startswith(("http://", "https://")):
        return origin
    shown = _resource((_edm(aip).get("Aggregation") or {}).get("isShownAt"))
    return shown if shown.startswith(("http://", "https://")) else ""


def images(aip: dict, limit: int = 50) -> tuple[int, list[dict]]:
    """The entry's digitised images (binaries): their count and the first ``limit``."""
    binaries = ((aip.get("binaries") or {}).get("binary")) or []
    rows = []
    for b in binaries:
        if not isinstance(b, dict):
            continue
        url = b.get("local_pathname")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        row: dict[str, Any] = {"position": b.get("position"), "url": url}
        if name := plain(b.get("name")):
            row["name"] = name
        if mime := b.get("mimetype"):
            row["mimetype"] = mime
        if license_ := b.get("kind"):
            row["license"] = license_
        rows.append(row)
    rows.sort(key=lambda r: r["position"] if isinstance(r["position"], int) else 10**9)
    return len(rows), rows[:limit]


def item(aip: dict) -> dict:
    """The parts of a DDB record worth returning, from ``/2/items/{id}``."""
    view = (aip.get("view") or {}).get("item") or {}
    cho = _edm(aip).get("ProvidedCHO") or {}
    props = aip.get("properties") or {}
    provider = aip.get("provider-info") or {}
    fields = display_fields(aip)
    institution = view.get("institution") or {}
    out: dict[str, Any] = {
        "id": props.get("item-id") or "",
        "title": plain(view.get("title")) or plain((cho.get("title") or {}).get("$")),
    }
    inst: dict[str, str] = {}
    if name := plain(institution.get("name")) or plain(provider.get("provider-name")):
        inst["name"] = name
    if url := institution.get("url") or provider.get("provider-uri"):
        inst["url"] = url
    if isil := provider.get("provider-isil"):
        inst["isil"] = str(isil).rsplit("/", 1)[-1]
    if inst:
        out["institution"] = inst
    identifiers = [i for i in cho.get("identifier") or [] if isinstance(i, str)]
    signature = fields.get("Archivaliensignatur") or (identifiers[0] if identifiers else "")
    if signature:
        out["signature"] = signature
    for label, key in (
        ("Bestand", "fonds"),
        ("Kontext", "context"),
        ("Laufzeit", "dates"),
        ("Umfang", "extent"),
    ):
        if fields.get(label):
            out[key] = fields[label]
    if "dates" not in out:
        dates = [d for d in cho.get("date") or [] if isinstance(d, str)]
        if dates:
            out["dates"] = dates[0]
    if level := cho.get("hierarchyType"):
        out["level"] = LEVELS.get(level, level)
    out["fields"] = fields
    return out


def hierarchy(parents: dict, own_id: str) -> tuple[list[dict], dict | None]:
    """The entry's ancestors from the top down, and the entry's own row, if listed.

    The own row carries ``leaf`` (nothing below it) and ``aggregationEntity``
    (a grouping node in the archive's structure, which has no record of its
    own at ``/items/{id}``).
    """
    rows = [h for h in (parents.get("hierarchy") or []) if isinstance(h, dict)]
    own = next((h for h in rows if h.get("id") == own_id), None)
    above = [
        {
            "id": h.get("id"),
            "title": plain(h.get("label")),
            "level": LEVELS.get(h.get("type") or "", h.get("type") or ""),
        }
        for h in rows
        if h.get("id") != own_id
    ]
    above.reverse()
    return above, own


def children(data: dict) -> tuple[int, list[dict]]:
    """What lies directly below an entry: the total and the rows returned."""
    rows = [h for h in (data.get("hierarchy") or []) if isinstance(h, dict)]
    # The API returns children in no stable order; "position" is the finding
    # aid's own order, as zero-padded digits.
    rows.sort(key=lambda h: str(h.get("position") or "").zfill(12))
    total = data.get("numberOfResults")
    shaped = [
        {
            "id": h.get("id"),
            "title": plain(h.get("label")),
            "level": LEVELS.get(h.get("type") or "", h.get("type") or ""),
            "has_children": not h.get("leaf", True),
        }
        for h in rows
    ]
    return (total if isinstance(total, int) else len(shaped)), shaped
