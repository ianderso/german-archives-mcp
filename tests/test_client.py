"""The HTTP client: what it sends, caches, refuses, retries and paces."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from german_archives_mcp import __version__
from german_archives_mcp.client import (
    APERTUS_HOST,
    DDB_HOST,
    LABW_HOST,
    LAGIS_HOST,
    NRW_PORTAL_HOST,
    PROJECT_URL,
    HostNotAllowed,
    SiteError,
    jpeg_size,
    looks_like_challenge,
    sniff_format,
    user_agent,
    write_new_image,
)

from .conftest import fixture, make_http, route_ddb, route_labw

SEARCH = f"https://{DDB_HOST}/2/search/index/search/select?q=Geburtsregister"
ITEM = f"https://{DDB_HOST}/2/items/6MOPYW4SNPH5WPLCP74BOLX6PX6NMSQG"
PLINK = f"https://{LABW_HOST}/ofs21/plink.php?f=5-475861"
THUMBS = f"https://{LABW_HOST}/ofs21/bild_zoom/thumbnails.php?bestand=10028&id=2239944"
BILD = f"https://{LABW_HOST}/ofs21/bild_zoom/bild.php?zoom=9"

#: The opening of the Anubis page the DDB's portal served on 2026-10-11.
ANUBIS = (
    '<!doctype html><html lang="en"><head><title>Making sure you&#39;re not a bot!'
    '</title><link rel="stylesheet" href="/.within.website/x/xess/xess.min.css">'
)


async def test_the_user_agent_names_the_package_version_and_repository(http, sites):
    route = route_ddb(sites)
    await http.get_json(SEARCH, ttl_days=1)
    agent = route.calls.last.request.headers["user-agent"]
    assert agent == f"german-archives-mcp/{__version__} (+{PROJECT_URL})"


def test_a_contact_is_appended_to_the_user_agent():
    assert user_agent("me@example.org").endswith(f"(+{PROJECT_URL}; me@example.org)")


async def test_json_and_html_requests_say_what_they_accept(http, sites):
    ddb, labw = route_ddb(sites), route_labw(sites)
    await http.get_json(SEARCH, ttl_days=1)
    await http.get_text(THUMBS, ttl_days=1)
    assert ddb.calls.last.request.headers["accept"] == "application/json"
    assert labw.calls.last.request.headers["accept"].startswith("text/html")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.deutsche-digitale-bibliothek.de/content/api-nutzungsbedingungen",
        "https://www.landesarchiv-bw.de/plink/?f=5-475861",
        "https://www.duesseldorf.de/stadtarchiv/archivenrw/7/0/7/x.jpg",
        f"http://{DDB_HOST}/2/items/X",
    ],
)
async def test_a_host_off_the_allowlist_is_refused_before_anything_is_sent(http, sites, url):
    with pytest.raises(HostNotAllowed):
        await http.get_json(url, ttl_days=1)
    with pytest.raises(HostNotAllowed):
        await http.fetch_image(url)
    with pytest.raises(HostNotAllowed):
        await http._http.get(url)


async def test_a_redirect_to_another_host_is_reported_not_followed(http, sites):
    target = "https://www.example.org/elsewhere"
    sites.route(host=DDB_HOST).mock(return_value=httpx.Response(302, headers={"location": target}))
    with pytest.raises(SiteError) as caught:
        await http.get_json(SEARCH, ttl_days=1)
    assert caught.value.code == "redirected" and caught.value.location == target


async def test_a_redirect_within_the_host_is_followed(http, sites):
    answers = iter(
        [
            httpx.Response(301, headers={"location": f"https://{DDB_HOST}/2/items/OTHER"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sites.route(host=DDB_HOST).mock(side_effect=lambda request: next(answers))
    assert await http.get_json(ITEM, ttl_days=1) == {"ok": True}


async def test_a_permalink_redirect_is_returned_not_followed(http, sites):
    route = route_labw(sites)
    hop = await http.get_location(PLINK, ttl_days=30)
    assert hop == {
        "status": 302,
        "location": "olf/struktur.php?bestand=10028&sprungId=2239944&letztesLimit=suchen",
    }
    assert route.call_count == 1


async def test_a_permalink_that_answers_a_page_returns_its_text(http, sites):
    route_labw(sites)
    hop = await http.get_location(f"https://{LABW_HOST}/ofs21/plink.php?f=5-1", ttl_days=30)
    assert hop["status"] == 200 and "keine Ressource" in hop["text"]


async def test_a_repeat_is_served_from_the_cache(http, sites):
    route = route_ddb(sites)
    first = await http.get_json(SEARCH, ttl_days=1)
    second = await http.get_json(SEARCH, ttl_days=1)
    assert first == second and route.call_count == 1
    assert (http.live_calls, http.cache_hits) == (1, 1)


async def test_a_permalink_redirect_is_cached(http, sites):
    route = route_labw(sites)
    await http.get_location(PLINK, ttl_days=30)
    await http.get_location(PLINK, ttl_days=30)
    assert route.call_count == 1


async def test_refresh_asks_again(http, sites):
    route = route_ddb(sites)
    await http.get_json(SEARCH, ttl_days=1)
    await http.get_json(SEARCH, ttl_days=1, refresh=True)
    assert route.call_count == 2


async def test_an_answer_expires_after_its_days(http, sites):
    route = route_ddb(sites)
    await http.get_json(SEARCH, ttl_days=1)
    for entry in http.cache_dir.glob("*.json"):
        data = json.loads(entry.read_text())
        data["stored"] = time.time() - 2 * 86_400
        entry.write_text(json.dumps(data))
    await http.get_json(SEARCH, ttl_days=1)
    assert route.call_count == 2


async def test_an_unreadable_cache_entry_is_fetched_again(http, sites):
    route = route_ddb(sites)
    await http.get_json(SEARCH, ttl_days=1)
    for entry in http.cache_dir.glob("*.json"):
        entry.write_text("{truncated")
    await http.get_json(SEARCH, ttl_days=1)
    assert route.call_count == 2


async def test_a_failure_is_not_cached(http, sites):
    answers = iter(
        [
            httpx.Response(404, json=fixture("ddb_item_not_found.json")),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sites.route(host=DDB_HOST).mock(side_effect=lambda request: next(answers))
    with pytest.raises(SiteError):
        await http.get_json(ITEM, ttl_days=7)
    assert await http.get_json(ITEM, ttl_days=7) == {"ok": True}


async def test_a_web_page_where_json_was_expected_is_not_json(http, sites):
    sites.route(host=DDB_HOST).mock(
        return_value=httpx.Response(200, text="<!DOCTYPE html><html></html>")
    )
    with pytest.raises(SiteError) as caught:
        await http.get_json(SEARCH, ttl_days=1)
    assert caught.value.code == "not_json" and "web page" in caught.value.detail


async def test_an_anubis_page_is_named_a_bot_check(http, sites):
    sites.route(host=DDB_HOST).mock(return_value=httpx.Response(200, text=ANUBIS))
    sites.route(host=LABW_HOST).mock(return_value=httpx.Response(200, text=ANUBIS))
    with pytest.raises(SiteError) as caught:
        await http.get_json(SEARCH, ttl_days=1)
    assert caught.value.code == "challenge"
    with pytest.raises(SiteError) as caught:
        await http.get_text(THUMBS, ttl_days=1)
    assert caught.value.code == "challenge"
    assert list(http.cache_dir.glob("*.json")) == []


async def test_a_cloudflare_challenge_is_named_a_bot_check(http, sites):
    sites.route(host=DDB_HOST).mock(
        return_value=httpx.Response(
            403, text="<title>Just a moment...</title>", headers={"cf-mitigated": "challenge"}
        )
    )
    with pytest.raises(SiteError) as caught:
        await http.get_json(SEARCH, ttl_days=1)
    assert caught.value.code == "challenge"


def test_a_page_that_merely_mentions_anubis_is_not_a_bot_check():
    assert not looks_like_challenge("<html><body>Statuette of Anubis, bronze</body></html>")
    assert looks_like_challenge(ANUBIS)


async def test_a_429_is_retried_once(http, sites):
    answers = iter([httpx.Response(429), httpx.Response(200, json={"ok": True})])
    route = sites.route(host=DDB_HOST).mock(side_effect=lambda request: next(answers))
    await http.get_json(SEARCH, ttl_days=1)
    assert route.call_count == 2


async def test_retry_after_is_honoured_and_capped(tmp_path, sites):
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    http = make_http(tmp_path, sleep=fake_sleep)
    answers = iter(
        [httpx.Response(429, headers={"retry-after": "120"}), httpx.Response(200, json={})]
    )
    sites.route(host=DDB_HOST).mock(side_effect=lambda request: next(answers))
    await http.get_json(SEARCH, ttl_days=1)
    assert waits == [30.0]


async def test_a_5xx_that_persists_gives_up_after_the_retry(http, sites):
    route = sites.route(host=DDB_HOST).mock(return_value=httpx.Response(503, text="down"))
    with pytest.raises(SiteError) as caught:
        await http.get_json(SEARCH, ttl_days=1)
    assert caught.value.status == 503 and route.call_count == 2
    assert http.last_error["status"] == 503


async def test_a_4xx_is_not_retried(http, sites):
    route = sites.route(host=DDB_HOST).mock(return_value=httpx.Response(404, json={}))
    with pytest.raises(SiteError) as caught:
        await http.get_json(ITEM, ttl_days=7)
    assert caught.value.status == 404 and route.call_count == 1


async def test_a_timeout_is_not_retried(tmp_path, sites):
    http = make_http(tmp_path, retries=3)
    route = sites.route(host=DDB_HOST).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(SiteError) as caught:
        await http.get_json(SEARCH, ttl_days=1)
    assert caught.value.code == "timeout" and route.call_count == 1


async def test_a_dropped_connection_is_retried(tmp_path, sites):
    http = make_http(tmp_path, retries=1)
    route = sites.route(host=DDB_HOST).mock(side_effect=httpx.ConnectError("reset"))
    with pytest.raises(SiteError) as caught:
        await http.get_json(SEARCH, ttl_days=1)
    assert caught.value.code == "no_response" and route.call_count == 2


async def test_an_answer_over_the_cap_is_refused(tmp_path, sites):
    http = make_http(tmp_path, max_text_bytes=100)
    sites.route(host=DDB_HOST).mock(return_value=httpx.Response(200, json={"x": "y" * 500}))
    with pytest.raises(SiteError) as caught:
        await http.get_json(SEARCH, ttl_days=1)
    assert caught.value.code == "too_large"


def _clocked(tmp_path, **kwargs):
    now = [100.0]
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    http = make_http(tmp_path, clock=lambda: now[0], sleep=fake_sleep, **kwargs)
    return http, now, waits


async def test_requests_to_one_host_are_spaced_by_the_minimum_interval(tmp_path, sites):
    http, now, waits = _clocked(tmp_path, min_interval=1.0)
    route_ddb(sites)
    await http.get_json(SEARCH, ttl_days=1)
    now[0] += 0.25
    await http.get_json(SEARCH + "&rows=2", ttl_days=1)
    assert waits == [pytest.approx(0.75)]


async def test_the_landesarchiv_is_never_asked_faster_than_its_floor(tmp_path, sites):
    http, now, waits = _clocked(tmp_path, min_interval=0.5, host_floors={LABW_HOST: 2.0})
    route_labw(sites)
    await http.get_text(THUMBS, ttl_days=1)
    await http.get_location(PLINK, ttl_days=1)
    assert waits == [pytest.approx(2.0)]
    assert http.interval(LABW_HOST) == 2.0 and http.interval(DDB_HOST) == 0.5


def test_by_default_no_host_is_asked_more_than_once_in_two_seconds(tmp_path):
    from german_archives_mcp.client import ALLOWED_HOSTS, ArchiveHttp

    http = ArchiveHttp(tmp_path, min_interval=0.5)
    assert {h: http.interval(h) for h in ALLOWED_HOSTS} == {h: 2.0 for h in ALLOWED_HOSTS}


def test_by_default_the_nrw_portals_searches_are_ten_seconds_apart(tmp_path):
    from german_archives_mcp.client import ArchiveHttp

    http = ArchiveHttp(tmp_path)
    assert http.search_interval(NRW_PORTAL_HOST) == 10.0
    assert http.search_interval(DDB_HOST) == 0.0


async def test_a_database_search_waits_for_the_last_search_not_just_the_last_request(
    tmp_path, sites
):
    floors = {NRW_PORTAL_HOST: (("/sufservice/api/search",), 10.0)}
    http, now, waits = _clocked(tmp_path, min_interval=2.0, search_floors=floors)
    sites.route(host=NRW_PORTAL_HOST).mock(return_value=httpx.Response(200, json={"hits": 0}))
    search = f"https://{NRW_PORTAL_HOST}/sufservice/api/search?keyword="
    await http.get_json(search + "a", ttl_days=1)
    await http.get_json(f"https://{NRW_PORTAL_HOST}/sufservice/api/other", ttl_days=1)
    await http.get_json(search + "b", ttl_days=1)
    # The other request waits the host's two seconds; the second search waits
    # until ten seconds have passed since the first.
    assert waits == [pytest.approx(2.0), pytest.approx(8.0)]


async def test_different_hosts_do_not_wait_for_each_other(tmp_path, sites):
    http, now, waits = _clocked(tmp_path, min_interval=1.0, host_floors={LABW_HOST: 2.0})
    route_ddb(sites)
    route_labw(sites)
    await http.get_json(SEARCH, ttl_days=1)
    await http.get_text(THUMBS, ttl_days=1)
    assert waits == []
    assert http.hosts_called == {DDB_HOST: 1, LABW_HOST: 1}


async def test_identical_concurrent_calls_share_one_request(http, sites):
    gate = asyncio.Event()

    async def slow(request):
        await gate.wait()
        return httpx.Response(200, json={"ok": True})

    route = sites.route(host=DDB_HOST).mock(side_effect=slow)
    first = asyncio.create_task(http.get_json(SEARCH, ttl_days=1))
    second = asyncio.create_task(http.get_json(SEARCH, ttl_days=1))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    gate.set()
    assert await first == await second
    assert route.call_count == 1 and http.shared_waits == 1


async def test_an_image_is_fetched_and_named_by_its_bytes(http, sites):
    route_labw(sites)
    body, kind = await http.fetch_image(BILD)
    assert kind == "jpeg" and body == fixture("labw_bild_182px.jpg")


async def test_an_image_that_is_not_an_image_is_refused(http, sites):
    sites.route(host=LABW_HOST).mock(return_value=httpx.Response(200, text="<html>Fehler</html>"))
    with pytest.raises(SiteError) as caught:
        await http.fetch_image(BILD)
    assert caught.value.code == "not_an_image"


async def test_an_image_over_the_cap_is_refused(http, sites):
    route_labw(sites)
    with pytest.raises(SiteError) as caught:
        await http.fetch_image(BILD, max_bytes=100)
    assert caught.value.code == "too_large"


def test_a_new_image_file_is_written_once(tmp_path):
    target = tmp_path / "page.jpg"
    body = fixture("labw_bild_182px.jpg")
    assert write_new_image(target, body, "jpeg") == len(body)
    with pytest.raises(FileExistsError):
        write_new_image(target, b"\xff\xd8\xff other", "jpeg")
    assert target.read_bytes() == body


def test_an_image_is_never_saved_under_the_wrong_suffix(tmp_path):
    with pytest.raises(SiteError) as caught:
        write_new_image(tmp_path / "page.png", fixture("labw_bild_182px.jpg"), "jpeg")
    assert caught.value.code == "extension_mismatch"
    assert not (tmp_path / "page.png").exists()


def test_formats_are_sniffed_from_bytes():
    assert sniff_format(b"\xff\xd8\xff\xe0") == "jpeg"
    assert sniff_format(b"\x89PNG\r\n\x1a\n") == "png"
    assert sniff_format(b"<html>") == "unknown"


def test_a_jpegs_size_is_read_from_its_header():
    assert jpeg_size(fixture("labw_bild_182px.jpg")) == (182, 136)
    assert jpeg_size(fixture("labw_bild_243px.jpg")) == (243, 182)
    assert jpeg_size(b"not a jpeg") is None
    assert jpeg_size(b"\xff\xd8\xff") is None


# --------------------------------------------------------------------------- #
# Form posts, file downloads and volume pacing (APERTUS, 0.3.0)
# --------------------------------------------------------------------------- #
APERTUS_SEARCH = f"https://{APERTUS_HOST}/queryOneExt.php"
APERTUS_UNIT = f"https://{APERTUS_HOST}/vz_php.php"
APERTUS_PDF = f"https://{APERTUS_HOST}/Bild/PStA_657,349_4.pdf"


async def test_a_form_post_is_sent_as_the_sites_own_form_and_cached(http, sites):
    route = sites.post(APERTUS_SEARCH).mock(
        return_value=httpx.Response(200, content="<b>Bestand </b> (1 von 1)".encode("latin-1"))
    )
    form = {"query": "Sterberegister+AND+Cochem", "rows": "25"}
    first = await http.post_text(APERTUS_SEARCH, form, ttl_days=1)
    second = await http.post_text(APERTUS_SEARCH, dict(reversed(list(form.items()))), ttl_days=1)
    assert first == second and route.call_count == 1
    sent = route.calls.last.request
    assert sent.headers["content-type"] == "application/x-www-form-urlencoded"
    assert b"query=Sterberegister%2BAND%2BCochem" in sent.content


async def test_a_post_whose_side_effect_matters_is_never_cached(http, sites):
    route = sites.post(APERTUS_UNIT).mock(return_value=httpx.Response(200, text="ok"))
    await http.post_text(APERTUS_UNIT, {"GUID": "x"}, ttl_days=0)
    await http.post_text(APERTUS_UNIT, {"GUID": "x"}, ttl_days=0)
    assert route.call_count == 2


async def test_a_post_that_redirects_is_an_error_never_followed(http, sites):
    sites.post(APERTUS_UNIT).mock(
        return_value=httpx.Response(302, headers={"location": "https://elsewhere.example/"})
    )
    with pytest.raises(SiteError) as caught:
        await http.post_text(APERTUS_UNIT, {"GUID": "x"}, ttl_days=0)
    assert caught.value.code == "redirected"


async def test_a_post_to_a_host_off_the_list_is_refused_unsent(http):
    with pytest.raises(HostNotAllowed):
        await http.post_text("https://elsewhere.example/form", {"a": "b"}, ttl_days=0)
    assert http.live_calls == 0


async def test_a_file_download_streams_to_its_target_and_leaves_no_part(http, sites, tmp_path):
    body = b"%PDF-1.4\n" + b"x" * 5_000
    sites.get(APERTUS_PDF).mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "application/pdf"})
    )
    target = tmp_path / "v" / "a.pdf"
    size, kind = await http.fetch_to_file(APERTUS_PDF, target, max_bytes=10_000)
    assert (size, kind) == (len(body), "application/pdf") and target.read_bytes() == body
    assert sorted(p.name for p in target.parent.iterdir()) == ["a.pdf"]
    assert sites.calls.last.request.headers["accept"] == "application/pdf"


@pytest.mark.parametrize("declared", [True, False])
async def test_a_download_over_the_limit_leaves_nothing(http, sites, tmp_path, declared):
    async def stream():
        for _ in range(10):
            yield b"0" * 1_000

    headers = {"content-length": "10000"} if declared else {}
    sites.get(APERTUS_PDF).mock(
        return_value=httpx.Response(
            200, content=stream() if not declared else b"0" * 10_000, headers=headers
        )
    )
    target = tmp_path / "a.pdf"
    with pytest.raises(SiteError) as caught:
        await http.fetch_to_file(APERTUS_PDF, target, max_bytes=4_000)
    assert caught.value.code == "too_large"
    assert list(tmp_path.iterdir()) == []


async def test_a_refused_download_leaves_nothing(http, sites, tmp_path):
    sites.get(APERTUS_PDF).mock(return_value=httpx.Response(404, text="gone"))
    with pytest.raises(SiteError) as caught:
        await http.fetch_to_file(APERTUS_PDF, tmp_path / "a.pdf", max_bytes=4_000)
    assert caught.value.status == 404 and list(tmp_path.iterdir()) == []


def test_by_default_apertus_searches_and_volumes_and_lagis_searches_wait_ten_seconds(tmp_path):
    from german_archives_mcp.client import ArchiveHttp

    http = ArchiveHttp(tmp_path)
    assert http.search_interval(APERTUS_HOST) == 10.0 and http.volume_interval(APERTUS_HOST) == 10.0
    assert http.search_interval(LAGIS_HOST) == 10.0 and http.volume_interval(LAGIS_HOST) == 0.0


async def test_opening_two_volumes_waits_for_the_last_volume(tmp_path, sites):
    floors = {APERTUS_HOST: (("/vz_php.php",), 10.0)}
    http, now, waits = _clocked(tmp_path, min_interval=2.0, volume_floors=floors)
    sites.post(APERTUS_UNIT).mock(return_value=httpx.Response(200, text="ok"))
    sites.post(APERTUS_SEARCH).mock(return_value=httpx.Response(200, text="ok"))
    await http.post_text(APERTUS_UNIT, {"GUID": "a"}, ttl_days=0)
    await http.post_text(APERTUS_SEARCH, {"q": "a"}, ttl_days=0)
    await http.post_text(APERTUS_UNIT, {"GUID": "b"}, ttl_days=0)
    # The search waits the host's two seconds; the second volume, until ten
    # seconds have passed since the first.
    assert waits == [pytest.approx(2.0), pytest.approx(8.0)]


async def test_a_slow_host_gets_a_longer_read_timeout(http, sites):
    seen = {}

    def answer(request):
        seen.update(request.extensions["timeout"])
        return httpx.Response(200, json={"results": []})

    sites.get(url__startswith=f"https://{LAGIS_HOST}/").mock(side_effect=answer)
    await http.get_json(f"https://{LAGIS_HOST}/de/api/gsearch/sn/x?suchbegriff=a", ttl_days=1)
    assert seen["read"] == 90.0


def test_an_imperva_page_is_a_challenge():
    page = "<html><head><script src='/_Incapsula_Resource?SWJIYLWA=1'></script></head></html>"
    assert looks_like_challenge(page)
