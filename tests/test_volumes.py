"""The volume-PDF cache, and taking a page's JPEG out of a volume unchanged."""

from __future__ import annotations

import io
import json
import os

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

from german_archives_mcp import volumes

from .conftest import FIXTURES

VOLUME = FIXTURES / "rlp_volume_657-349_4.pdf"
A = "00000000-0000-4000-8000-00000000000a"
B = "00000000-0000-4000-8000-00000000000b"
C = "00000000-0000-4000-8000-00000000000c"


class Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def _cache(tmp_path, clock, *, days=3.0, max_bytes=10_000) -> volumes.VolumeCache:
    return volumes.VolumeCache(
        tmp_path / "volumes", max_age_days=days, max_bytes=max_bytes, clock=clock
    )


def _store(cache: volumes.VolumeCache, key: str, size: int, clock: Clock) -> None:
    path = cache.pdf_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-" + b"0" * (size - 5))
    cache.put(key, 1, {"guid": key})
    os.utime(path, (clock.now, clock.now))


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def test_a_volume_counts_its_pages():
    assert volumes.count_pages(VOLUME) == 3


def test_a_page_is_the_archives_jpeg_byte_for_byte():
    jpeg = volumes.page_jpeg(VOLUME, 2)
    assert jpeg == (FIXTURES / "nrw_bild_250px.jpg").read_bytes()
    assert volumes.page_jpeg(VOLUME, 3) == (FIXTURES / "hla_bild_150px.jpg").read_bytes()


def test_a_page_past_the_end_is_refused():
    with pytest.raises(volumes.VolumeError) as caught:
        volumes.page_jpeg(VOLUME, 4)
    assert caught.value.code == "no_such_page" and "3 pages" in str(caught.value)


def test_something_that_is_not_a_pdf_is_named_for_what_it_is(tmp_path):
    page = tmp_path / "x.pdf"
    page.write_bytes(b"<html>Fehler</html>")
    with pytest.raises(volumes.VolumeError) as caught:
        volumes.count_pages(page)
    assert caught.value.code == "not_a_pdf"
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\n" + b"\x00" * 200)
    with pytest.raises(volumes.VolumeError) as caught:
        volumes.page_jpeg(broken, 1)
    assert caught.value.code == "not_a_pdf"


def test_an_image_that_is_not_a_jpeg_is_not_converted(tmp_path):
    writer = PdfWriter(clone_from=PdfReader(VOLUME))
    image = next(iter(writer.pages[0]["/Resources"]["/XObject"].values())).get_object()
    image[NameObject("/Filter")] = NameObject("/JPXDecode")
    out = io.BytesIO()
    writer.write(out)
    path = tmp_path / "jpx.pdf"
    path.write_bytes(out.getvalue())
    with pytest.raises(volumes.VolumeError) as caught:
        volumes.page_jpeg(path, 1)
    assert caught.value.code == "unsupported_image" and "JPXDecode" in str(caught.value)
    assert volumes.page_jpeg(path, 2)[:3] == b"\xff\xd8\xff"


# --------------------------------------------------------------------------- #
# The cache
# --------------------------------------------------------------------------- #
def test_a_stored_volume_is_found_until_it_expires(tmp_path):
    clock = Clock()
    cache = _cache(tmp_path, clock)
    _store(cache, A, 100, clock)
    got = cache.get(A)
    assert got is not None and got.pages == 1 and got.meta == {"guid": A} and got.size == 100
    clock.now += 2.9 * 86_400
    assert cache.get(A) is not None
    clock.now += 0.2 * 86_400
    assert cache.get(A) is None
    assert not cache.pdf_path(A).exists(), "an expired volume is deleted when found expired"


def test_reading_a_volume_marks_it_recently_read(tmp_path):
    clock = Clock()
    cache = _cache(tmp_path, clock)
    _store(cache, A, 100, clock)
    clock.now += 60
    cache.get(A)
    assert cache.pdf_path(A).stat().st_mtime == pytest.approx(clock.now)


def test_pruning_removes_expired_volumes_then_the_least_recently_read(tmp_path):
    clock = Clock()
    cache = _cache(tmp_path, clock, max_bytes=2_500)
    _store(cache, A, 1_000, clock)
    clock.now += 10
    _store(cache, B, 1_000, clock)
    clock.now += 10
    _store(cache, C, 1_000, clock)
    removed = cache.prune(keep=C)
    assert removed == [A], "over the cap, the least recently read goes first"
    clock.now += 4 * 86_400
    assert set(cache.prune(keep=C)) == {B}, "past the lifetime everything goes but the one in use"
    assert cache.pdf_path(C).exists()


def test_the_volume_being_read_is_never_pruned_even_alone_over_the_cap(tmp_path):
    clock = Clock()
    cache = _cache(tmp_path, clock, max_bytes=500)
    _store(cache, A, 1_000, clock)
    assert cache.prune(keep=A) == []
    assert cache.pdf_path(A).exists()


def test_a_pdf_without_its_description_is_cleared_away(tmp_path):
    clock = Clock()
    cache = _cache(tmp_path, clock)
    cache.root.mkdir(parents=True)
    cache.pdf_path(A).write_bytes(b"%PDF-1.4")
    assert cache.get(A) is None
    assert cache.prune() == [A] and not cache.pdf_path(A).exists()


def test_an_unreadable_description_is_a_miss_not_a_crash(tmp_path):
    clock = Clock()
    cache = _cache(tmp_path, clock)
    _store(cache, A, 100, clock)
    (cache.root / f"{A}.json").write_text("{not json")
    assert cache.get(A) is None
    (cache.root / f"{A}.json").write_text(json.dumps({"stored": "yesterday", "pages": 1}))
    assert cache.get(A) is None


def test_old_unfinished_downloads_are_removed(tmp_path):
    clock = Clock()
    cache = _cache(tmp_path, clock)
    cache.root.mkdir(parents=True)
    part = cache.root / f".{A}.pdf.abc.part"
    part.write_bytes(b"%PDF-")
    os.utime(part, (clock.now - 2 * 86_400, clock.now - 2 * 86_400))
    cache.prune()
    assert not part.exists()


@pytest.mark.parametrize(
    "key", ["../../etc/passwd", "a" * 36, "", "00000000-0000-4000-8000-00000000000A"]
)
def test_a_key_that_is_not_a_guid_never_becomes_a_file_name(tmp_path, key):
    cache = _cache(tmp_path, Clock())
    with pytest.raises(ValueError):
        cache.pdf_path(key)


def test_status_counts_what_is_on_disk(tmp_path):
    clock = Clock()
    cache = _cache(tmp_path, clock, max_bytes=5_000_000)
    _store(cache, A, 1_500_000, clock)
    status = cache.status()
    assert status["volumes"] == 1 and status["megabytes"] == 1.5
    assert status["cap_megabytes"] == 5.0 and status["kept_days"] == 3.0
