# german-archives-mcp

[![CI](https://github.com/ianderso/german-archives-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ianderso/german-archives-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/german-archives-mcp)](https://pypi.org/project/german-archives-mcp/)

<!-- mcp-name: io.github.ianderso/german-archives-mcp -->

An [MCP](https://modelcontextprotocol.io) server for **German archives'
finding aids and the vital registers German state archives have put
online**: search what German archives, libraries and museums have described
in the [Deutsche Digitale Bibliothek](https://www.deutsche-digitale-bibliothek.de)
and its archive portal [Archivportal-D](https://www.archivportal-d.de), read
one entry with its place in the archive's fonds, find the civil or church
register of a place for a year at the
[Landesarchiv Baden-Württemberg](https://www.landesarchiv-bw.de), the
[Landesarchiv Nordrhein-Westfalen](https://www.archive.nrw.de/landesarchiv-nrw),
the [Landesarchivverwaltung Rheinland-Pfalz](https://lav.rlp.de) or the
[Hessisches Landesarchiv](https://landesarchiv.hessen.de), and download a page
of it to read.

The DDB is Germany's counterpart of DPLA, and for archives its counterpart of
ArchiveGrid as well: archives deliver their finding aids to it, item by item,
with signatures (call numbers), dates and the fonds each item belongs to. Some
deliver images. Its version 2 API answers without a key.

The server covers every fonds of vital registers the **Landesarchiv
Baden-Württemberg** has online (the Staatsarchiv Wertheim's civil-register
duplicates, from 1870, are not yet in its online finding aids):

| Fonds | Department | What it holds |
| --- | --- | --- |
| **L 10** | Staatsarchiv Freiburg | Baden Standesbücher, south Baden: the civil duplicates of the parish registers, 1810-1870, one book per parish and confession for a span of years |
| **390** | Generallandesarchiv Karlsruhe | Baden Standesbücher, north Baden |
| **F 901** | Staatsarchiv Ludwigsburg | Duplicates of Württemberg's Catholic parish registers, 1808-1875, one volume per register |
| **Wü 110 T 1** | Staatsarchiv Sigmaringen | Duplicates of the Protestant parish registers of Württemberg and Hohenzollern, 1808-1875 |
| **J 386** | Hauptstaatsarchiv Stuttgart | Films (1943-1945) of the registers of the Jewish communities of Baden, Württemberg and Hohenzollern, whose originals are lost |
| **Dep. 1 T 37**, **Dep. 1 T 44** | Staatsarchiv Sigmaringen | Civil registers of the Standesamt Sigmaringen and Sigmaringen-Laiz, digitised for 1870-1899 |

The **Landesarchiv Nordrhein-Westfalen** has put its civil registers
(Zivilstands- and Personenstandsregister) online: the Rhineland's from 1798,
and Westphalia's and Lippe's with some of their church-book duplicates, as
far as the protection periods allow (births 110 years, marriages 80, deaths
30). The server searches them through the Archive in NRW portal and reads
their pages from the Landesarchiv's image server.

The **Landesarchivverwaltung Rheinland-Pfalz**'s Personenstandsarchiv, part
of the Landeshauptarchiv Koblenz, has put the civil registers of the state's
north online in its virtual reading room
[APERTUS](https://apertus.rlp.de): Best. 657,001 onward, one fonds per
Standesamt or Bürgermeisterei, mostly the former government districts of
Koblenz and Trier, from 1798. About 59,000 birth, marriage and death registers
have images there: by the archive's count (March 2026) some 32,000 whole
registers, digitised district by district up to 1880 or 1895, and 28,000
registers of which only the name index is digitised. APERTUS delivers a
register only as one PDF of the whole volume, so the server downloads a volume
once, keeps it on disk for a few days, and takes each page asked for out of
it.

The **Hessisches Landesarchiv**'s Personenstandsarchiv keeps the secondary
registers of every Standesamt in today's Hesse, from 1874 or 1876, in fonds
HStAM 900 to 926, and has put them online to 1900 (births), 1930 (marriages)
and 1965 (deaths). The server finds them in the catalogue of the
[Landesgeschichtliches Informationssystem Hessen (LAGIS)](https://lagis.hessen.de)
and reads their pages from [Arcinsys Hessen](https://arcinsys.hessen.de).

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
Baden-Württemberg, the Landesarchiv Nordrhein-Westfalen, the
Landesarchivverwaltung Rheinland-Pfalz, the Hessisches Landesarchiv, LAGIS, or
any archive whose finding aids it reads.

## Tools

The server publishes eleven tools. All but the four image tools are
read-only; each of those writes one new file and never overwrites one
(`rlp_image` also keeps the volume PDFs it downloads in the cache folder).

**The Deutsche Digitale Bibliothek and Archivportal-D**

| Tool | Purpose |
| --- | --- |
| `ddb_search` | Search finding aids and digitised objects. Each hit names the holding institution, its signature, the dates, where it sits in its fonds, and whether it has images. Filters: sector (archive, library, museum...), the holder's name, images only, years. |
| `ddb_item` | One entry in full: every field the archive delivered, its path from the archive down through the fonds, what lies below it (for a fonds or series), links to its images on the holder's site, rights, and a citation naming the archive, signature and the archive's own page. |

**The registers at the Landesarchiv Baden-Württemberg**

| Tool | Purpose |
| --- | --- |
| `labw_standesbuch` | The books for a place, a year, a confession and (optionally) one fonds: signature (`L 10 Nr. 510`, `F 901 Bd 1511`, `Wü 110 T 1 Nr. 4566`, `J 386 Bü 583`), fonds, title, the parish heading, years, registers, confession, district court (Baden), permalink, whether it has images, and the image count. Villages filed under a larger place are included, and marked. |
| `labw_image` | One page image, by signature or permalink and image number, saved as a new `.jpg`, with its citation: "Landesarchiv Baden-Württemberg, Abt. Staatsarchiv Freiburg, L 10 Nr. 510, Bild 378" and the image's permalink. Works for any Landesarchiv item with images, given its permalink. |

**The civil registers at the Landesarchiv Nordrhein-Westfalen**

| Tool | Purpose |
| --- | --- |
| `nrw_search` | Search the Archive in NRW portal (the Landesarchiv's three departments, or every archive in the portal): title, archive, signature (`PA 2104 Nr. 267`, `P 3 / 9 Nr. 260`), dates, fonds, permalink, and for a digitised unit its METS address and whether `nrw_image` can read it. |
| `nrw_image` | One page image of a Landesarchiv NRW unit, by its METS address and image number, saved as a new `.jpg`, with its citation: "Landesarchiv NRW Abteilung Rheinland, PA 2104 Nr. 267, Bild 12", the permalink and the URN. |

**The civil registers in Rheinland-Pfalz (APERTUS)**

| Tool | Purpose |
| --- | --- |
| `rlp_search` | Search the Personenstandsarchiv's digitised units in APERTUS by place, Bürgermeisterei or Standesamt, register type and years: signature (`Best. 657,377 Nr. 141`), title (`Sterberegister der Bürgermeisterei Cochem-Land`), years, dates, permalink, and the `item` `rlp_image` takes. |
| `rlp_image` | One page of a unit, by its `item`, permalink or signature and the page of its PDF, saved as a new `.jpg`, with its citation: "Landesarchivverwaltung Rheinland-Pfalz, Landeshauptarchiv Koblenz, Best. 657,349 Nr. 4 (...), PDF page 3" and the permalink. The first page of a volume downloads the whole volume's PDF (tens of megabytes, up to a minute); later pages come from disk. |

**The civil registers in Hesse (LAGIS and Arcinsys)**

| Tool | Purpose |
| --- | --- |
| `hessen_search` | Search LAGIS's catalogue of the Hessisches Landesarchiv's digitised registers by place (a village finds its Standesamt's registers), register type and year: title (`Korbach, Geburtsnebenregister, 1880`), Standesamt, years, signature (`HStAM 922 Nr. 6013`) and LAGIS link. |
| `hessen_image` | One page image of a register, by signature or Arcinsys address and image number, saved as a new `.jpg`, with its citation: "Hessisches Staatsarchiv Marburg, HStAM 922 Nr. 6013 (...), Bild 2" and the Arcinsys permalink. Works for any Arcinsys Hessen unit of the three state archives with images. |

**Housekeeping**

| Tool | Purpose |
| --- | --- |
| `cache_status` | This session's requests, by host, the pacing, cache use and the volume PDFs on disk. Makes no request. |

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
| `GERMAN_ARCHIVES_CACHE_DIR` | Response cache directory, and the home of the APERTUS volume PDFs (`volumes/`). Default `~/.cache/german-archives-mcp`. |
| `GERMAN_ARCHIVES_TIMEOUT` | HTTP timeout in seconds for one request. Default 30. Image downloads get 120 to read. |
| `GERMAN_ARCHIVES_MIN_INTERVAL` | Least seconds between two requests to one host. Default 2, never below 2. Searches on the Archive in NRW portal, APERTUS and LAGIS, and APERTUS volume downloads, always wait at least 10. |
| `GERMAN_ARCHIVES_CONTACT` | An email address or URL added to the User-Agent, so an archive can reach you if your use causes trouble. Optional, and courteous. |
| `GERMAN_ARCHIVES_DOWNLOAD_DIR` | An existing folder. When set, the image tools save only inside it. Set it to save into an iCloud Drive folder, which lives under `~/Library`. |
| `GERMAN_ARCHIVES_PDF_CACHE_DAYS` | Days a downloaded APERTUS volume PDF is kept for reading further pages. Default 3, at most 30. |
| `GERMAN_ARCHIVES_PDF_CACHE_MB` | Most megabytes of volume PDFs kept; past it the volumes read least recently are deleted. Default 1000, at least 100. A volume larger than this is not downloaded. |

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
- **A Baden Standesbuch is a civil copy of the parish register, 1810 to
  1870; a Württemberg duplicate, 1808 to 1875.** Before, look for the parish
  register itself; after, the civil registry office. A Baden book often covers
  several years and all three registers, and sometimes two confessions
  (`confessions`); a Württemberg volume holds one register (`registers`).
- **`labw_standesbuch` finds books by the place the archive files them
  under.** In Baden and J 386 the place is in the book's title; in F 901 and
  Wü 110 T 1 it is the parish heading above the volume (`place`). A village
  incorporated into a town is filed under both names (`Niederrimsingen,
  Breisach am Rhein FR`; `Einsingen, Ulm UL`), so a search for the town lists
  its villages too; `place_named_first` says which books are the place's own.
  Two places can share a name: Ulm in Württemberg and two Ulms in Baden.
  Spell the place as the archive does, umlauts included.
- **`has_images: false`** means the volume is described but not online. In
  Wü 110 T 1, `{1754: nicht vorhanden}` marks a duplicate that was never
  delivered.
- **J 386 is film, not the original.** The Reichssippenamt filmed the Jewish
  registers in 1943-1945; the originals are lost, so the film is the surviving
  witness. Cite the film's signature.
- **An NRW search covers descriptions.** Registers are described by
  Standesamt (or, before 1815, Mairie or Bürgermeisterei), register type and
  year: search `Geburtsregister Barmen`, not a person's name. Years match by
  overlap. Only the Landesarchiv's own units are read by `nrw_image`; other
  archives' digitised units come back with a DFG-Viewer link to open in a
  browser.
- **`page` is the archive's image number ("Bild"), counted from 1,** not the
  number written on the page. In NRW it is the image's place in the METS
  file, which the archive's viewer shows in the same order. A book's image numbers and its permalinks can
  fall out of step where an image was added later: in L 10 Nr. 510, Bild 119
  is permalink `…-380`, and Bild 378 is `…-377`. `labw_image` reads the
  archive's own list, so either works.
- **APERTUS files a register under its Bürgermeisterei or Standesamt.**
  Search the office's name (`Cochem` finds `Cochem-Land` and `Cochem-Stadt`);
  `rlp_search` covers the units with images, mostly from the former
  government districts of Koblenz and Trier. Some units' images are only the
  register's name index; `rlp_image` passes on the archive's note.
- **`rlp_image`'s `page` is the page of the volume's PDF,** one scan per page,
  often a two-page spread. The first page of a volume costs the archive a
  whole volume (6 to 27 MB in the registers seen), so read several pages of
  one volume rather than one page each of many; the volume stays on disk for
  `GERMAN_ARCHIVES_PDF_CACHE_DAYS`. The page saved is the archive's own JPEG,
  taken out of the PDF unchanged.
- **LAGIS matches every word against the register's title and the places of
  its Standesamt district,** so a village finds its Standesamt's registers. A
  `year` matches only a register whose title names it: a volume binding
  several years needs no year. LAGIS orders hits by relevance, 25 at most a
  page.
- **`hessen_image`'s `page` is the image's place in Arcinsys's viewer.**
  Pages still under a protection period (an adoption, an acknowledged
  paternity) are left out of the online register, so an image's file name
  can be one ahead of its place; the citation gives both.
- **Read the page.** These registers are handwritten, mostly in German
  script. The image is the evidence; nothing in this server transcribes it.

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
with its rights (the viewer shows the Public Domain Mark 1.0 for every fonds
listed above, checked 2026-10-11), and ask every user to "Archivsignatur
oder den Permalink zitieren". They also ask for a deposit copy of a book made
with substantial use of the archive's material (§ 8 Abs. 9
Landesarchivgesetz). They say nothing about automated access. As a fact:
`robots.txt` on `www2.landesarchiv-bw.de` allows Googlebot and Yahoo and
disallows everyone else. The DDB's copy of the Landesarchiv's entries lists
the images as CC BY 3.0 DE; the archive's own viewer marks them Public
Domain, and `labw_image` reports the archive's mark.

**Landesarchiv Nordrhein-Westfalen.** Its terms for content and digitised
records
([Nutzungsbedingungen, PDF](https://www.landesarchiv-nrw.de/digitalisate/LAV_NRW_Nutzungsbedingungen_Digitalisate.pdf))
put its finding aids under CC0 and its digitised records under CC BY-SA;
digitised records "dürfen von der Webseite in der bereitgestellten Auflösung
kostenlos heruntergeladen werden", and every reuse must cite the signature,
and online the permalink. Each METS file repeats the licence. The terms say
nothing about automated access. As facts: `robots.txt` on
`www.archive.nrw.de` disallows the site's own `/search/` page and
administrative paths, not the `/sufservice/` search service this server
calls; `www.landesarchiv-nrw.de` has no `robots.txt` (404). No bot check was
met on either host.

**Landesarchivverwaltung Rheinland-Pfalz (APERTUS).** APERTUS's help says
that every digital version of archival material in it is free to download
("stehen in APERTUS zum kostenlosen Download zur Verfügung",
[Hilfe > Download](https://apertus.rlp.de/hilfe.php)), and the archive's fee
page says downloads from APERTUS are free of charge
([Dienstleistungen und Gebühren](https://lav.rlp.de/finden-und-benutzen/benutzungshinweise/dienstleistungen-und-gebuehren)).
Its decree on publication
([Allgemeinverfügung zu Veröffentlichungsgenehmigungen, PDF](https://lav.rlp.de/fileadmin/lav/Bilder/Finden_und_Benutzen/Archivgut_im_Lesesaal/Allgemeinverfuegung_zur_Veroeffentlichungsgenehmigungen.pdf))
says records free for unrestricted use need no permission to publish, asks
that the sources be cited (§ 10 Abs. 1 LArchBVO), politely asks for a copy,
waives publication fees, and forbids unlawful, defamatory or extremist use, as
APERTUS's [disclaimer](https://apertus.rlp.de/Disclaimer.php) does. Nothing
on automated access. As a fact: `apertus.rlp.de` has no `robots.txt` (404).
No bot check was met; the search and unit pages answered without a cookie.

**Hessisches Landesarchiv (Arcinsys Hessen, LAGIS).** The archive says its
digitised civil registers can be seen in Arcinsys free of charge and without
registration, and that single pages may be downloaded as JPG
([Recherche in digitalisierten Personenstandsnebenregistern](https://landesarchiv.hessen.de/ueber-uns/personenstandsarchiv-hessen/recherche-digitalisierte-personenstandsnebenregister));
use of reproductions published online is free of charge
([Kosten und Gebühren](https://landesarchiv.hessen.de/nutzen-forschen/kosten-gebuehren)).
No licence for the images is published: each METS file's licence field is
empty, and Arcinsys's [imprint](https://arcinsys.hessen.de/arcinsys/information.action)
notes only that some content is protected by copyright. LAGIS gives its
catalogue data as CC0 and a citation form for each entry. Nothing on automated
access was found in either. As facts: `arcinsys.hessen.de/robots.txt` names
only a sitemap; `digitalisate-he.arcinsys.de/robots.txt` disallows everything
for every agent; `www.lagis-hessen.de/robots.txt` disallows named crawlers and
some search pages, not `/de/api/`. No bot check was met; no session, form
state or script was needed.

**What the client does.** It sends one request at a time to each host, at
least two seconds apart, and holds the searches that run on an archive's own
database (the Archive in NRW portal's, APERTUS's and LAGIS's) at least ten
seconds apart, and the opening of two APERTUS volumes, each of which makes the
archive build and send a whole PDF, at least ten seconds apart. Two identical
calls in flight share one request. Searches are cached for a day, DDB records
for a week, and the Landesarchiv Baden-Württemberg's permalink answers and
image lists, the Landesarchiv NRW's and Arcinsys's METS files and the
signature look-ups for 30 days, so reading a second page of a book costs one
request. An APERTUS volume is downloaded once and kept for three days (within
a 1000 MB cap; both configurable), so its later pages cost none. A 429, a 5xx
or a dropped connection gets one retry, honouring `Retry-After`. The
User-Agent names the package, its version and this repository; no other
client is imitated. Images are fetched at the size the archive's viewer
shows, and written to your file, never cached.

## Deliberately not here

- **The DDB's portal, newspapers and user features.** The portal is behind a
  bot check; favourites and saved searches need an account.
- **Images on the holders' own sites.** `ddb_item` and `nrw_search` return
  their links; this server fetches nothing outside its four hosts.
- **Other states' registers, for now.** Berlin's are on Ancestry, Saarland's
  and Bavaria's are not online at their state archives, and Thuringia's and
  Saxony's church books are on Archion. See
  [docs/DESIGN.md](docs/DESIGN.md#other-state-archives).
- **Resizing.** `rlp_image` and `hessen_image` save the archive's JPEG as it
  is; making it smaller would need an imaging library.
- **Matricula.** Its church books span several countries and deserve a server
  of their own.
- **Transcription.** The page is read by a person, or by a tool built for
  German script.
- **Working around bot checks.** A site that answers with one is reported as
  `blocked` and left alone.

## Security

Tool arguments are written by a model, and the model reads text this server
does not control: finding-aid entries, image links, web pages. The server
assumes that text can steer the model, and limits what a steered model can
make it do.

- **Which hosts.** Eight, fixed: `api.deutsche-digitale-bibliothek.de`,
  `www2.landesarchiv-bw.de`, `www.archive.nrw.de`,
  `www.landesarchiv-nrw.de`, `apertus.rlp.de`, `www.lagis-hessen.de`,
  `arcinsys.hessen.de` and `digitalisate-he.arcinsys.de`. Any other host is
  refused before it is looked up, including addresses that come back in a
  response, such as an image link in a DDB record, a viewer link in an NRW
  hit, a PDF path in an APERTUS answer, an image in a METS file, or a
  redirect. A permalink redirect is read, never followed.
- **Which addresses.** Each connection is checked where it is made: a name
  that leads to a private, loopback, link-local, CGNAT, multicast, reserved or
  unspecified address, IPv4 or IPv6, is refused, and the connection goes to
  the address that was checked. Proxy settings in the environment are not
  used.
- **How much.** A JSON, HTML or XML answer over 10 MB, an image over 60 MB,
  or a volume PDF over `GERMAN_ARCHIVES_PDF_CACHE_MB` (and never over 500
  MB), is refused as it streams in. A search returns at most 50 hits a page.
- **What is sent.** Search words have Solr's field, range and parameter
  syntax escaped; a place must be letters, spaces and a few punctuation
  marks; ids and signatures are matched against narrow patterns; an image is
  asked for only by a file name the archive's own list gave, and only if it
  has the archive's file-name shape; an NRW or Hessian image only by an
  address its METS file gave, on the archive's image server, ending in
  `.jpg`, with no `..` and no query; an APERTUS volume only by the `/Bild/`
  path the unit's own description gave, of the archive's file-name shape. A
  cached volume's file name is the unit's GUID, checked against its pattern.
- **Which files.** The four image tools each create one new file and
  never overwrite one; `rlp_image` also writes volume PDFs inside the cache
  folder, nowhere else.
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
Baden-Württemberg, the Landesarchiv Nordrhein-Westfalen, the
Landesarchivverwaltung Rheinland-Pfalz and the Hessisches Landesarchiv are the
state archives of Baden-Württemberg, North Rhine-Westphalia,
Rhineland-Palatinate and Hesse; the Archive in NRW portal is run by the
Landesarchiv NRW for the archives of the state; LAGIS is run by the Hessisches
Landesamt für geschichtliche Landeskunde; Arcinsys was built by the Hessisches
and the Niedersächsisches Landesarchiv.

## License

[MIT](LICENSE).
