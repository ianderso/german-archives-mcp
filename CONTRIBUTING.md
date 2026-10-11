# Contributing

Issues and pull requests are welcome. This file says how the project is put
together and what a change is expected to carry.

## Setting up

```bash
git clone https://github.com/ianderso/german-archives-mcp
cd german-archives-mcp
uv sync --extra dev
```

Before sending a change, run what CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The suite is mocked with [respx](https://lundberg.github.io/respx/) against
recorded responses. It must never touch a live site: CI should not depend on
the DDB or the Landesarchiv being up, and neither should be asked for more
than a person would ask.

## Where things live

| Path | What it holds |
| --- | --- |
| `src/german_archives_mcp/server.py` | The tools. Their docstrings and `Field` descriptions *are* the published tool descriptions and schema. |
| `src/german_archives_mcp/ddb.py` | The DDB's version 2 API: search addresses, filters, and shaping hits, records, hierarchies and children. |
| `src/german_archives_mcp/labw.py` | The Landesarchiv: the two Standesbücher fonds, signatures, permalinks, the image list, the image address and the citation. |
| `src/german_archives_mcp/client.py` | The cached, paced HTTP client, the two-host allowlist, the redirect rule, the public-address check made at connect time, the size caps and bot-check detection. |
| `src/german_archives_mcp/config.py` | Settings from the environment and `.env`. |
| `docs/API-NOTES.md` | What each site was observed to do, and when. |
| `docs/DESIGN.md` | Why the server is shaped the way it is, and what is out of scope by decision. |
| `tests/fixtures/` | Recorded responses and the tool-schema snapshot. |
| `tests/test_tool_contract.py` | Tests over the tool surface as a client sees it. |
| `tests/test_security.py` | Every refusal against a steered model: hosts, addresses, sizes, files. |
| `tests/live_check.py` | The one script that talks to live sites, run by hand. Not collected. |

## What a change carries

**A test that fails without it.** Bug fixes especially: reproduce the bug as a
test first.

**Descriptions written for the model.** A tool's docstring is what a model
reads when choosing and calling it. The combined descriptions have a ceiling
(`DESCRIPTION_BUDGET` in `tests/test_tool_contract.py`), because they are sent
on every session. Raise it deliberately, in a pull request of its own. They
are dedented at import, so the budget measures the same text on every Python.

**The evidence distinction, kept.** A finding-aid entry says where a record is,
not what it says; a page image is the evidence. Tools that return entries say
so; a contract test enforces it.

**A citation on every record.** Any result that names a record carries the
archive, its signature and an address: the archive's own page or permalink
where there is one.

**A structured result, never an exception.** Every tool catches its failures
and returns an `error` envelope. A sweep test calls every tool with both sites
failing and fails if one raises.

**Nothing that writes to a site, and nothing that works around a bot check.**
See [docs/DESIGN.md](docs/DESIGN.md#out-of-scope-by-decision).

**Nothing that widens what an argument can reach.** Treat every argument as
written by someone else's text. A new host goes into `ALLOWED_HOSTS` only with
a reason in the pull request, a new place to write only through
`server._destination`, and each comes with a test in `tests/test_security.py`
showing that the refusals still come before the harm.

**A new fixture recorded, not invented,** when a change depends on how a site
answers, with what was observed and when added to `docs/API-NOTES.md`. Keep
fixtures to registers and finding-aid headings, and choose example places and
archives unconnected with your own research.

**The snapshot, when the surface changes.** Renaming or adding a tool or a
parameter fails the snapshot test on purpose. Regenerate it with
`uv run python -m tests.regen_tool_snapshot`, update the README tables, and add
a `CHANGELOG.md` entry.

## Adding a Landesarchiv fonds

`labw.FONDS` names the two Standesbücher fonds. Another digitised fonds
already works in `labw_image` through its permalink. To let `labw_standesbuch`
search one, or `labw_image` take its signatures, add an entry: its signature
prefix as the DDB writes it (`apd_reference_number`), and the online finding
aid's ids for it, which a permalink redirect (`bestand`) and an image address
(`scopeid_besta`) show. Record both in `docs/API-NOTES.md`, and add a live
check.

## Releasing

A maintainer bumps `__version__` in `src/german_archives_mcp/__init__.py` and
both versions in `server.json`, moves the changelog's Unreleased entries under
the new version, and publishes a GitHub release tagged `v<version>`. The
release workflow builds the tag, publishes to PyPI by Trusted Publishing, and
lists the version in the MCP Registry.
