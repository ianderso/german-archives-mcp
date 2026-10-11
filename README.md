# german-archives-mcp

[![CI](https://github.com/ianderso/german-archives-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ianderso/german-archives-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/german-archives-mcp)](https://pypi.org/project/german-archives-mcp/)

<!-- mcp-name: io.github.ianderso/german-archives-mcp -->

An [MCP](https://modelcontextprotocol.io) server for **German archives'
finding aids and Baden's civil registers**: search what German archives,
libraries and museums have described in the
[Deutsche Digitale Bibliothek](https://www.deutsche-digitale-bibliothek.de)
and its archive portal [Archivportal-D](https://www.archivportal-d.de), read
one entry with its place in the archive's fonds, find the Standesbuch of a
Baden parish for a year at the
[Landesarchiv Baden-Württemberg](https://www.landesarchiv-bw.de), and
download a page of it to read.

The DDB is Germany's counterpart of DPLA, and for archives its counterpart of
ArchiveGrid as well: archives deliver their finding aids to it, item by item,
with signatures (call numbers), dates and the fonds each item belongs to. Some
deliver images. Its version 2 API answers without a key.

The Landesarchiv has put the **Baden Standesbücher** online in full: the
civil duplicates of the parish registers of baptisms, marriages and burials
that Baden's clergy kept from 1810 to 1870, one book per parish and
confession for a span of years. South Baden's are fonds **L 10** at the
Staatsarchiv Freiburg; north Baden's are fonds **390** at the
Generallandesarchiv Karlsruhe. The server covers both.

It works the way a careful genealogist does. **A finding-aid entry says where
a record is, not what it says**: cite the archive and its signature, not the
DDB. **The page image is the evidence**: read it before citing it, and cite
the archive, the signature and the image number with the archive's
permalink. **A zero is not a negative**: most German registers are not
online, and many archives deliver nothing to the DDB.

Nothing here writes anywhere, and nothing here keeps a family tree. It sits
beside [dpla-catalog-mcp](https://github.com/ianderso/dpla-catalog-mcp) for
American collections and
[snac-archives-mcp](https://github.com/ianderso/snac-archives-mcp) for
finding which archive holds a family's papers.

This is an independent project. It is not affiliated with, endorsed by, or
supported by the Deutsche Digitale Bibliothek, the Landesarchiv
Baden-Württemberg, or any archive whose finding aids it reads.

## Tools

The server publishes five tools. All but `labw_image` are read-only;
`labw_image` writes one new file and never overwrites one.

**The Deutsche Digitale Bibliothek and Archivportal-D**

| Tool | Purpose |
| --- | --- |
| `ddb_search` | Search finding aids and digitised objects. Each hit names the holding institution, its signature, the dates, where it sits in its fonds, and whether it has images. Filters: sector (archive, library, museum...), the holder's name, images only, years. |
| `ddb_item` | One entry in full: every field the archive delivered, its path from the archive down through the fonds, what lies below it (for a fonds or series), links to its images on the holder's site, rights, and a citation naming the archive, signature and the archive's own page. |

**The Baden Standesbücher at the Landesarchiv Baden-Württemberg**

| Tool | Purpose |
| --- | --- |
| `labw_standesbuch` | The books for a place, a year and a confession: signature (`L 10 Nr. 510`, `390 Nr. 1875`), title, years, district court, permalink and image count. Villages filed under the municipality they now belong to are included, and marked. |
| `labw_image` | One page image, by signature or permalink and image number, saved as a new `.jpg`, with its citation: "Landesarchiv Baden-Württemberg, Abt. Staatsarchiv Freiburg, L 10 Nr. 510, Bild 378" and the image's permalink. Works for any Landesarchiv item with images, given its permalink. |
| `cache_status` | This session's requests, by host, and cache use. Makes no request. |

## Setup

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/). There is
no key to request.

**Without cloning.** `uvx` fetches it from PyPI and runs it in one step:

```bash
uvx german-archives-mcp
```

**From a clone**, which is what you want if you will change it:

```bash
git clone https://github.com/ianderso/german-archives-mcp
cd german-archives-mcp
uv sync
uv run german-archives-mcp   # stdio server, usually launched by the client
```

Either way the server speaks MCP over stdio, so you will normally let an MCP
client start it rather than run it by hand.

### Claude Desktop

```json
{
  "mcpServers": {
    "german-archives": {
      "command": "uvx",
      "args": ["german-archives-mcp"]
    }
  }
}
```

A desktop app does not always inherit your shell's `PATH`. If the server fails
to start because `uvx` cannot be found, give the full path that `which uvx`
prints as the `command`.

### Claude Code

```bash
claude mcp add german-archives -- uvx german-archives-mcp
```

## Configuration

Nothing is required. A `.env` file in the directory the server starts in
supplies anything the environment does not; only that directory is read.

| Variable | Meaning |
| --- | --- |
| `GERMAN_ARCHIVES_CACHE_DIR` | Response cache directory. Default `~/.cache/german-archives-mcp`. |
| `GERMAN_ARCHIVES_TIMEOUT` | HTTP timeout in seconds for one request. Default 30. Image downloads get 120 to read. |
| `GERMAN_ARCHIVES_MIN_INTERVAL` | Least seconds between two requests to one host. Default 1, never below 0.5. The Landesarchiv's site always gets at least 2. |
| `GERMAN_ARCHIVES_CONTACT` | An email address or URL added to the User-Agent, so an archive can reach you if your use causes trouble. Optional, and courteous. |
| `GERMAN_ARCHIVES_DOWNLOAD_DIR` | An existing folder. When set, `labw_image` saves only inside it. Set it to save into an iCloud Drive folder, which lives under `~/Library`. |

An unusable value is reported on the first tool call as a `not_configured`
result naming the variable.

## How to read what comes back

- **A DDB entry is a finding aid.** The archive wrote it to say where a
  record is and roughly what it holds. It supports a research task (order the
  file, open the images), not a fact. Cite the archive and its signature
  (`citation` in `ddb_item`), and the archive's own page where the entry
  links one; keep the DDB id only as a finder.
- **A DDB search covers descriptions, never page text,** and only what
  archives have delivered. Many German archives deliver nothing, and most
  that do describe registers by volume, not by name. No hits is not a
  negative.
- **`archive` matches the start of the holder's name, exactly as the DDB
  writes it**, capitals and umlauts included: `Stadtarchiv Düsseldorf`, not
  `stadtarchiv duesseldorf`.
- **Dates match by overlap.** `year_to: 1812` keeps a register for 1811-1816.
- **A series heading has no record of its own.** `ddb_item` then answers with
  its place in the hierarchy and its children (`grouping_node`).
- **The DDB lists only the first ten images of a Landesarchiv item.**
  `labw_image` reads every page; `ddb_search` and `ddb_item` give the
  permalink it takes (`labw_permalink`).
- **A Standesbuch is a civil copy of the parish register, 1810 to 1870.**
  Before 1810, look for the parish register itself; after 1870, the civil
  registry office. A book often covers several years, and sometimes two
  confessions (`confessions`).
- **`labw_standesbuch` finds books whose title names the place.** A village
  incorporated into a town is filed under both names (`Niederrimsingen,
  Breisach am Rhein FR`), so a search for the town lists its villages too;
  `place_named_first` says which books are the place's own. Spell the place
  as the archive does, umlauts included.
- **`page` is the archive's image number ("Bild"), counted from 1,** not the
  number written on the page. A book's image numbers and its permalinks can
  fall out of step where an image was added later: in L 10 Nr. 510, Bild 119
  is permalink `…-380`, and Bild 378 is `…-377`. `labw_image` reads the
  archive's own list, so either works.
- **Read the page.** Standesbücher are handwritten in German script. The
  image is the evidence; nothing in this server transcribes it.

## Terms of use, and being a good guest

**Deutsche Digitale Bibliothek.** The DDB's developer documentation says its
data is "publically accessible without any restrictions"
([DDB-Backend / API](https://deutsche-digitale-bibliothek.atlassian.net/wiki/spaces/DDBDOK/pages/47831240/DDB-Backend+API))
and that "using version 2 all endpoints are usable without an API key"
([Differences between API versions 1 and 2](https://deutsche-digitale-bibliothek.atlassian.net/wiki/spaces/DDBDOK/pages/47831182/Differences+between+API+versions+1+and+2)).
Its OpenAPI description says metadata delivered through the API is licensed
CC0, while images carry each institution's own licence. Two older pages still
describe a key: the DDBpro page on its interfaces and the general text of the
OpenAPI description; the version 2 routes this server uses declare no
security and answered without one on 2026-10-11. The former API terms page
(`/content/terms/api`) now answers 404, and the DDB's portal sits behind an
Anubis proof-of-work check, which this server never touches: it reaches only
the API host. No rate limit is published. The API host has no `robots.txt`
(it answers 404). If the DDB starts refusing keyless requests, the tools say
`key_required`.

**Landesarchiv Baden-Württemberg.** Its terms
([Nutzungsbedingungen auf einen Blick](https://www.landesarchiv-bw.de/de/recherche/rechtsgrundlagen---nutzungsbedingungen/auf-einen-blick))
put the online finding aids' metadata under CC0, mark each digitised item
with its rights (the Standesbücher viewer shows the Public Domain Mark 1.0),
and ask every user to "Archivsignatur oder den Permalink zitieren". They also
ask for a deposit copy of a book made with substantial use of the archive's
material (§ 8 Abs. 9 Landesarchivgesetz). They say nothing about automated
access. As a fact: `robots.txt` on `www2.landesarchiv-bw.de` allows Googlebot
and Yahoo and disallows everyone else. The DDB's copy of the Landesarchiv's
entries lists the images as CC BY 3.0 DE; the archive's own viewer marks
them Public Domain, and `labw_image` reports the archive's mark.

**What the client does.** It sends one request at a time to each host: the
DDB's at least a second apart, the Landesarchiv's at least two. Two
identical calls in flight share one request. Searches are cached for a day,
DDB records for a week, and the Landesarchiv's permalink answers and image
lists for 30 days, so reading a second page of a book costs one request. A
429, a 5xx or a dropped connection gets one retry, honouring `Retry-After`.
The User-Agent names the package, its version and this repository. Images
are rendered at the size the archive's viewer shows at 100 per cent, and
written to your file, never cached.

## Deliberately not here

- **The DDB's portal, newspapers and user features.** The portal is behind a
  bot check; favourites and saved searches need an account.
- **Images on the holders' own sites.** `ddb_item` returns their links; this
  server fetches nothing outside its two hosts.
- **Transcription.** The page is read by a person, or by a tool built for
  German script.
- **Working around bot checks.** A site that answers with one is reported as
  `blocked` and left alone.

## Security

Tool arguments are written by a model, and the model reads text this server
does not control: finding-aid entries, image links, web pages. The server
assumes that text can steer the model, and limits what a steered model can
make it do.

- **Which hosts.** Two, fixed: `api.deutsche-digitale-bibliothek.de` and
  `www2.landesarchiv-bw.de`. Any other host is refused before it is looked
  up, including addresses that come back in a response, such as an image link
  in a DDB record or a redirect. A permalink redirect is read, never
  followed.
- **Which addresses.** Each connection is checked where it is made: a name
  that leads to a private, loopback, link-local, CGNAT, multicast, reserved or
  unspecified address, IPv4 or IPv6, is refused, and the connection goes to
  the address that was checked. Proxy settings in the environment are not
  used.
- **How much.** A JSON or HTML answer over 10 MB, or an image over 60 MB, is
  refused as it streams in. A search returns at most 50 hits a page.
- **What is sent.** Search words have Solr's field, range and parameter
  syntax escaped; a place must be letters, spaces and a few punctuation
  marks; ids and signatures are matched against narrow patterns; an image is
  asked for only by a file name the archive's own list gave, and only if it
  has the archive's file-name shape.
- **Which files.** `labw_image` creates one new file and never overwrites one.
  The bytes must be an image, judged by their first bytes, and a JPEG, since
  the file must end in `.jpg` or `.jpeg`. Never a hidden file or folder,
  never under `~/Library`, and with `GERMAN_ARCHIVES_DOWNLOAD_DIR` set, never
  outside it, all judged after links are resolved. A refused download leaves
  nothing on disk.
- **Site text is untrusted.** Titles and descriptions reach the model
  verbatim. The server's instructions tell the model to treat that text as
  material to weigh, never as instructions; the model still decides, so
  review what it proposes to do.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development

```bash
uv sync --extra dev
uv run pytest                      # mocked with respx; never touches a site
uv run ruff check .
uv run ruff format --check .
uv run python -m tests.live_check  # paced calls to the live sites
```

The live check asks the sites what the recorded fixtures cannot: whether
their answers still have the shape the server reads. See
[CONTRIBUTING.md](CONTRIBUTING.md) for how the suite is organised,
[docs/API-NOTES.md](docs/API-NOTES.md) for what was observed of each site and
when, and [docs/DESIGN.md](docs/DESIGN.md) for why the server is shaped this
way.

## Credits

The finding aids belong to the archives that wrote them, and the images to
the archives that hold the records. The Deutsche Digitale Bibliothek is run
by a network of German cultural institutions; the Landesarchiv
Baden-Württemberg is the state archive of Baden-Württemberg.

## License

[MIT](LICENSE).
