"""Whole-volume PDFs kept on disk for a while, and the page images inside them.

APERTUS delivers a unit's images only as one PDF of the whole volume, which
it builds when the unit is opened and deletes again within minutes. Reading
one page therefore costs the archive a whole volume (6 to 27 MB in the
registers seen). To ask for each volume once, not once per page, the server
keeps every PDF it downloads under ``<cache dir>/volumes/`` for
``GERMAN_ARCHIVES_PDF_CACHE_DAYS`` (default 3) and within
``GERMAN_ARCHIVES_PDF_CACHE_MB`` (default 1000): past the lifetime a volume is
deleted, and past the cap the volumes read least recently go first.

The volumes are Ghostscript's PDF 1.4 files, one scanned page per PDF page,
each a single JPEG image (``DCTDecode``). A page is read by taking that JPEG
out of the file as it is: no rasterising and no re-encoding, so the page
saved is the archive's scan, byte for byte. That is :mod:`pypdf`'s part; it
is pure Python and the only reason this server depends on it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

logger = logging.getLogger("german_archives_mcp.volumes")

_DAY = 86_400.0

#: A cache key: a unit's GUID.
_KEY = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

#: How deep page images are looked for inside form XObjects.
_MAX_DEPTH = 3


class VolumeError(RuntimeError):
    """A volume or page that cannot be read: ``not_a_pdf``, ``no_such_page``,
    ``unsupported_image``."""

    def __init__(self, code: str, message: str):
        """Record the kind of failure."""
        self.code = code
        super().__init__(message)


@dataclass
class Volume:
    """One cached volume: its PDF, its page count and what the archive said of it."""

    key: str
    path: Path
    pages: int
    meta: dict[str, Any]
    stored: float

    @property
    def size(self) -> int:
        """Bytes on disk."""
        try:
            return self.path.stat().st_size
        except OSError:
            return 0


class VolumeCache:
    """Volume PDFs under one folder, each beside a small JSON file describing it.

    Parameters
    ----------
    root : Path
        The folder. Created on first write.
    max_age_days : float
        Days a volume is kept after it was downloaded.
    max_bytes : int
        Most bytes of PDFs kept; the least recently read go first.
    clock : callable, optional
        Wall-clock time, for tests.
    """

    def __init__(self, root: Path, *, max_age_days: float, max_bytes: int, clock=time.time) -> None:
        self.root = root
        self.max_age = max_age_days * _DAY
        self.max_bytes = max_bytes
        self._clock = clock

    def pdf_path(self, key: str) -> Path:
        """Where a volume's PDF lives."""
        return self.root / f"{_checked(key)}.pdf"

    def _meta_path(self, key: str) -> Path:
        return self.root / f"{_checked(key)}.json"

    def get(self, key: str) -> Volume | None:
        """A fresh volume, marked as just read, or None if absent, expired or unreadable."""
        pdf, meta_path = self.pdf_path(key), self._meta_path(key)
        try:
            entry = json.loads(meta_path.read_text(encoding="utf-8"))
            size = pdf.stat().st_size
        except (OSError, ValueError):
            return None
        stored = entry.get("stored") if isinstance(entry, dict) else None
        pages = entry.get("pages") if isinstance(entry, dict) else None
        if not isinstance(stored, int | float) or not isinstance(pages, int) or size == 0:
            return None
        if self._clock() - stored > self.max_age:
            self.remove(key)
            return None
        now = self._clock()
        try:
            os.utime(pdf, (now, now))
        except OSError:
            pass
        return Volume(key, pdf, pages, entry.get("meta") or {}, stored)

    def put(self, key: str, pages: int, meta: dict[str, Any]) -> Volume:
        """Record the PDF already at :meth:`pdf_path` as a volume of ``pages`` pages."""
        stored = self._clock()
        entry = {"stored": stored, "pages": pages, "meta": meta}
        _write_atomically(self._meta_path(key), json.dumps(entry, ensure_ascii=False))
        return Volume(key, self.pdf_path(key), pages, meta, stored)

    def remove(self, key: str) -> None:
        """Delete a volume and its description."""
        for path in (self.pdf_path(key), self._meta_path(key)):
            path.unlink(missing_ok=True)

    def _entries(self) -> list[tuple[str, float, float, int]]:
        """(key, stored, last read, bytes) for every volume on disk."""
        out = []
        try:
            files = list(self.root.glob("*.pdf"))
        except OSError:
            return out
        for pdf in files:
            key = pdf.stem
            if not _KEY.fullmatch(key):
                continue
            try:
                stat = pdf.stat()
                entry = json.loads(self._meta_path(key).read_text(encoding="utf-8"))
                stored = float(entry["stored"])
            except (OSError, ValueError, KeyError, TypeError):
                stored = 0.0
                try:
                    stat = pdf.stat()
                except OSError:
                    continue
            out.append((key, stored, stat.st_mtime, stat.st_size))
        return out

    def prune(self, keep: str | None = None) -> list[str]:
        """Delete expired volumes, then the least recently read until within the cap.

        ``keep`` (the volume being read) is never deleted. Returns the keys
        removed. Unfinished downloads older than a day are removed too.
        """
        removed = []
        now = self._clock()
        entries = self._entries()
        for key, stored, _, _ in entries:
            if key != keep and now - stored > self.max_age:
                self.remove(key)
                removed.append(key)
        live = sorted(
            (e for e in entries if e[0] not in removed), key=lambda e: e[2]
        )  # least recently read first
        total = sum(e[3] for e in live)
        for key, _, _, size in live:
            if total <= self.max_bytes:
                break
            if key == keep:
                continue
            self.remove(key)
            removed.append(key)
            total -= size
        try:
            for part in self.root.glob(".*.part"):
                if now - part.stat().st_mtime > _DAY:
                    part.unlink(missing_ok=True)
        except OSError:
            pass
        return removed

    def status(self) -> dict[str, Any]:
        """What is cached, for ``cache_status``."""
        entries = self._entries()
        return {
            "folder": str(self.root),
            "volumes": len(entries),
            "megabytes": round(sum(e[3] for e in entries) / 1_000_000, 1),
            "cap_megabytes": round(self.max_bytes / 1_000_000, 1),
            "kept_days": round(self.max_age / _DAY, 2),
        }


def _checked(key: str) -> str:
    """A cache key, refused unless it is a GUID: it becomes a file name."""
    if not _KEY.fullmatch(key or ""):
        raise ValueError(f"not a volume key: {key!r}")
    return key


def _write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def count_pages(path: Path) -> int:
    """How many pages a downloaded PDF has.

    Raises
    ------
    VolumeError
        ``not_a_pdf`` if the file is not a PDF pypdf can read.
    """
    try:
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise VolumeError("not_a_pdf", "the archive sent a file that is not a PDF")
            handle.seek(0)
            return len(PdfReader(handle).pages)
    except VolumeError:
        raise
    except (PyPdfError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise VolumeError(
            "not_a_pdf", f"the PDF could not be read ({type(exc).__name__})"
        ) from None


def page_jpeg(path: Path, number: int) -> bytes:
    """The JPEG image of page ``number`` (from 1), taken out of the PDF unchanged.

    The page's largest image is taken. It must be a JPEG (``DCTDecode``,
    possibly behind other filters, which are undone); the scan is returned as
    the archive stored it.

    Raises
    ------
    VolumeError
        ``no_such_page``, ``not_a_pdf``, or ``unsupported_image`` if the page
        holds no JPEG image.
    """
    try:
        with path.open("rb") as handle:
            reader = PdfReader(handle)
            if not 1 <= number <= len(reader.pages):
                raise VolumeError(
                    "no_such_page",
                    f"page {number} is out of range; the volume has {len(reader.pages)} pages",
                )
            images = _images(reader.pages[number - 1], 0)
            if not images:
                raise VolumeError("unsupported_image", f"page {number} holds no image")
            _, image, filters = max(images, key=lambda i: i[0])
            if not filters or filters[-1] != "/DCTDecode":
                raise VolumeError(
                    "unsupported_image",
                    f"page {number}'s image is not a JPEG ({', '.join(filters) or 'unfiltered'});"
                    " this server saves the archive's scan unchanged and does not convert it",
                )
            data = image.get_data()
    except VolumeError:
        raise
    except (PyPdfError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise VolumeError(
            "not_a_pdf", f"the PDF could not be read ({type(exc).__name__})"
        ) from None
    if not data.startswith(b"\xff\xd8\xff"):
        raise VolumeError("unsupported_image", f"page {number}'s image is not a readable JPEG")
    return data


def _images(holder: Any, depth: int) -> list[tuple[int, Any, list[str]]]:
    """(area, image, filters) for every image a page or form XObject draws from its resources."""
    found: list[tuple[int, Any, list[str]]] = []
    resources = holder.get("/Resources")
    resources = resources.get_object() if resources is not None else None
    xobjects = resources.get("/XObject") if resources is not None else None
    if xobjects is None:
        return found
    for _, ref in xobjects.get_object().items():
        obj = ref.get_object()
        subtype = obj.get("/Subtype")
        if subtype == "/Image":
            raw = obj.get("/Filter")
            raw = raw.get_object() if raw is not None else None
            if raw is None:
                filters = []
            elif isinstance(raw, list):
                filters = [str(f) for f in raw]
            else:
                filters = [str(raw)]
            try:
                area = int(obj.get("/Width", 0)) * int(obj.get("/Height", 0))
            except (TypeError, ValueError):
                area = 0
            found.append((area, obj, filters))
        elif subtype == "/Form" and depth < _MAX_DEPTH:
            found += _images(obj, depth + 1)
    return found
