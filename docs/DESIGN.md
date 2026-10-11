# Design

Why the server is shaped the way it is, and what is out of scope by decision.

## The questions it answers

"Which German archive holds a record of this place, and under what
signature?" and "Is the register for this parish and year online, and what
does the page say?"

German archival records are scattered across thousands of state, municipal,
and private archives, few of which put registers online. Many deliver
their finding aids to the Deutsche Digitale Bibliothek, which shows them in
Archivportal-D and serves them through one keyless API: that is the nearest
thing Germany has to a union catalogue of archives, and the core of this
server. Four state archives have put whole series of registers online behind
machinery a client can read: the Landesarchiv Baden-Württemberg (Baden's
Standesbücher, Württemberg's and Hohenzollern's church-book duplicates, the
films of the Jewish registers), the Landesarchiv Nordrhein-Westfalen (the
civil registers of the Rhineland, Westphalia and Lippe), the
Landesarchivverwaltung Rheinland-Pfalz (the civil registers of the state's
north, in APERTUS) and the Hessisches Landesarchiv (the secondary civil
registers of every Hessian Standesamt, catalogued in LAGIS and shown in
Arcinsys). Those are the rest.

## Five sources, eleven tools

- `ddb_search` and `ddb_item` are the DDB half, shaped like
  [dpla-catalog-mcp](https://github.com/ianderso/dpla-catalog-mcp)'s
  `search_items` and `get_item`: a search that returns citable hits, and a
  record read in full. A DDB archival entry also sits in a hierarchy (archive,
  holdings overview, fonds, series, unit), which DPLA records do not, so
  `ddb_item` returns the path down to the entry and, for a fonds or a series,
  what lies below it. That is how a finding aid is browsed.
- `labw_standesbuch` and `labw_image` are the Landesarchiv
  Baden-Württemberg's pair: find the book, then read one page of it. 0.1.0
  covered Baden's two fonds; 0.2.0 covers every register fonds in the same
  online finding aids, behind the same two tools, with an optional `fonds`
  argument. The names stayed, so 0.1.0's callers keep working.
- `nrw_search` and `nrw_image` are the Landesarchiv NRW's pair, of the same
  shape. They are separate tools rather than more arguments to the
  Landesarchiv Baden-Württemberg's, because the two archives find a register
  differently (by place in the DDB's copy of a finding aid; by keyword in a
  portal) and identify a page differently (a signature and a viewer's image
  list; a METS file), and a model reads one description per archive more
  easily than one description that tells two apart.
- `rlp_search` and `rlp_image` (0.3.0) are the Landesarchivverwaltung
  Rheinland-Pfalz's pair, over APERTUS: its unit search, and one page of a
  unit, which APERTUS serves only inside a PDF of the whole volume.
- `hessen_search` and `hessen_image` (0.3.0) are Hesse's pair: the search
  reads LAGIS's catalogue of the digitised registers, the image tool reads
  Arcinsys's METS file and image server. Two sites behind one pair, because
  together they are how the Hessisches Landesarchiv itself sends a user from
  a register to its pages.
- `cache_status` is the house tool for what a session has asked of each
  host, and what volume PDFs are on disk.

The tool count stays small on purpose: the descriptions are sent on every
session (about 4,650 characters for eleven tools), and a model chooses better
among a few tools than among many. A further archive gets a pair of its own
only if its registers cannot be reached through an existing one. Each pair
here finds and identifies a register differently (a DDB copy of a finding
aid; a portal's keyword search and METS; a PHP application's form posts and
a volume PDF; a catalogue's API and an archive system's METS), which is the
reason for separate pairs rather than more arguments to one.

## Finding a register through the DDB

The Landesarchiv's online finding aids (OLF) offer a structure view and a
search form, but no API. Its finding aids are also delivered to the DDB,
under CC0, with each book's signature, title, years, context path and a
`provider_item_id` (`labw-5-475861`) that is the Landesarchiv's own scope id,
from which the permalink follows. So `labw_standesbuch` asks the DDB one
question and asks the Landesarchiv only for the image counts of the first
four books that have images. The alternative, walking the structure views,
would mean several requests per question to the archive's own server and a
place-to-heading table to maintain for each fonds.

Which fonds: the DDB was asked which Landesarchiv fonds are registers and
have images (2026-10-11). Seven are: L 10, 390, F 901, Wü 110 T 1, J 386,
Dep. 1 T 37 and Dep. 1 T 44 (`labw.FONDS`). The Staatsarchiv Wertheim's
Personenstandszweitbücher (K-LRA 30, from 1870) have only an intranet
finding aid, and the Catholic duplicates of Hohenzollern's parishes are in
none of them.

Where the place is: the fonds arrange their books differently.

- In Baden, J 386 and the Sigmaringen deposits the place is in the title
  (`Breisach am Rhein FR; Katholische Gemeinde: Standesbücher 1848-1854`,
  `Ulm`, `Geburtenregister Sigmaringen`), so a phrase search on the title
  finds it.
- In F 901 and Wü 110 T 1 the title names only the register (`Taufregister
  VI`, `Eheregister vom 3.5.1808 - 8.6.1875`) and the place is the heading
  above it, the last step of the context path (`... >> 17.29 Rottenburg am
  Neckar TÜ`, `... >> Reutlingen RT`). For those two fonds the query also
  phrase-searches `apd_context`. It does not for Baden, where the context is
  the district court and would bring every book of the court.

So one query serves every fonds: `title:"X" OR (apd_reference_number:(F 901
OR Wü 110 T 1) AND apd_context:"X")`, filtered to the seven fonds, to units
(fonds and series headings are left out) and to the year by overlap. Each row
carries its `place` (the heading, numbering dropped), and a village filed
under a larger place carries both names (`Niederrimsingen, Breisach am Rhein
FR`, `Einsingen, Ulm UL`), so `place_named_first` tells the place's own books
from its villages'. Confession is the fonds' own where every book shares it
(F 901 Catholic, Wü 110 T 1 Protestant, J 386 Jewish, the deposits civil) and
read from the title in Baden, where it is written. Rows are ordered: the
place's own books first, then by fonds, place, first year and number.

## Reading a page at the Landesarchiv Baden-Württemberg

`labw_image` uses the three steps the archive's own viewer uses, the same
for every fonds: the
permalink redirect, which names the fonds and the book's id in the OLF; the
thumbnail page, which lists every image's file name in order; and the image
script, which renders one file as a JPEG at a zoom percentage. Two findings
shaped it:

- **An image's number and its file name can disagree.** In L 10 Nr. 510, an
  image was added after the book was scanned: Bild 119's file ends in 380,
  and every image after it ends one behind its place. Guessing file names
  from the image number would fetch the wrong page and cite it confidently.
  So the image list is read (and cached for 30 days) and Bild *n* is its
  *n*th entry, and an image permalink is matched by the number its file name
  ends in.
- **The image script takes a server path as a parameter.** The server never
  passes one it built from an argument: the file name must come from the
  archive's own list and match the archive's file-name pattern, and the
  folder is built from numbers alone. A hostile option value in the list is
  ignored.

Zoom 100 is the size the archive's viewer shows; it upscales beyond that, so
the server never asks for more. `max_pixels` costs one more request: the
first image says the full size, and the second is asked for at the zoom that
fits.

The DDB's records of Landesarchiv books list only their first ten images,
exported to a static folder for Europeana. They are not used for reading.

F 901's viewer is an older one (it crops through `bild2.php`), but the
standard image script renders its files too, so `labw_image` does not need
to know.

## Searching and reading at the Landesarchiv NRW

The Archive in NRW portal's search page is a script over a keyless JSON
service, `/sufservice/api/search`, which takes a keyword, the archive's
number, years, a digitised-only flag, a page and a size. `nrw_search` calls
it as the page does and shapes each hit; the archive filter is offered for
the Landesarchiv's three departments, and left empty searches every archive
in the portal. Its searches run on the archive's own database, so the client
holds them ten seconds apart.

A digitised hit carries a DFG-Viewer link whose `tx_dlf[id]` is the unit's
METS file. For the Landesarchiv's own units the METS file and the page images
are on `www.landesarchiv-nrw.de`; the METS file lists the pages as JPEGs in
its `DEFAULT` group, in the order of its physical structure map, and names
the unit (`Abteilung Rheinland, PA 2104 (...), Nr. 267`), its id (from which
the permalink follows), its URN and its licence. So `nrw_image` takes the
METS address, reads it once (cached 30 days), and fetches the *n*th image.
Other archives' METS files are on their own servers (the Stadtarchiv
Düsseldorf's on `www.duesseldorf.de`) and are returned as links: reading them
would mean an open-ended host list.

The images are static JPEGs at the viewer's size (about 1,800 by 2,600 pixels
for a register page, 0.2 to 0.9 MB), so `nrw_image` has no `max_pixels`: the
server would have to resize locally, which needs an imaging library.

The permalink (`/ms/search?link=VERZEICHUNGSEINHEIT-Vz_<id>`) cannot be turned
back into a METS address with one request: the portal's lookup by node
returns the archive's whole tree (300 KB, four seconds). So `nrw_image` asks
for the METS address that `nrw_search` returns, and refuses a permalink with
a message that says so.

## Reading a register in Rheinland-Pfalz: APERTUS's whole-volume PDF

APERTUS (`apertus.rlp.de`) is a PHP application whose pages are HTML
fragments fetched by form posts from the site's own scripts. Two of them are
enough, and both answered without a cookie, a token or a preceding page:

- `queryOneExt.php` lists units. Its form takes the query as the site's own
  search form rewrites it (words joined with `+AND+`), an optional fonds and
  number (which makes it a signature look-up), a year range (`range`,
  `range2`), a digitised-only flag, an offset and a page size. With no fonds,
  it lists matching units across every fonds in one answer, so `rlp_search`
  is one request; the facet step the site's own interface makes first
  (`queryfacet.php`, counts per fonds) is skipped. An answer of a bare line
  break means nothing matched.
- `vz_php.php` describes a unit by its GUID and, as a side effect, makes the
  archive build the unit's images as one PDF of the whole volume under
  `/Bild/`, which it deletes again about five minutes later. There is no page
  route: the site's viewer script mentions a single-page call
  (`imgviewer.php`), but no register unit uses it.

So reading one page means having the archive build and send the whole volume
(6 to 27 MB in the registers seen; a year's births of a small town took 40
seconds to download). That cost was accepted on the condition that
each volume is fetched once: `rlp_image` opens the unit, downloads the PDF to
`<cache dir>/volumes/<GUID>.pdf` and keeps it there for
`GERMAN_ARCHIVES_PDF_CACHE_DAYS` (default 3) within
`GERMAN_ARCHIVES_PDF_CACHE_MB` (default 1000, least recently read first), so
every later page of the volume is read from disk with no request at all. Two
pages asked for at once share one download (a lock per GUID); a signature
is looked up once and remembered for 30 days; a volume larger than the cap
is not downloaded. Opening a unit counts as a volume request, held ten
seconds from the last (`client.VOLUME_FLOORS`); searches are held ten seconds
apart too.

The PDFs are Ghostscript's, PDF 1.4, one scanned page per PDF page, each a
single JPEG image (`DCTDecode`). `volumes.page_jpeg` takes that JPEG out as
it is, through pypdf, so the saved page is the archive's scan byte for byte:
no rasterising, no re-encoding and no imaging library. That is also why
`rlp_image` has no `max_pixels`: shrinking a page would need an imaging
library (Pillow) and would re-encode the archive's scan. A page whose image
is not a JPEG is refused as `unsupported_image` rather than converted.

`page` is the PDF's page. The PDF holds the scans in the viewer's order, one
per page, often a two-page spread, so the archive's own viewer shows the same
numbering; the citation says "PDF page" so no one mistakes it for a folio.
Some units' images are only the register's name index ("Digitalisat: Nur
Namensverzeichnis"); `rlp_image` passes on the archive's notes and says so.

## Reading a register in Hesse: LAGIS and Arcinsys

The 0.2.0 survey found Arcinsys's signature search sending a scripted request
back to its empty form and concluded that a client would have to replay the
application's form state. It does not: that form is only one way in. Read
with plain HTTP, Arcinsys has three routes that need no session, no
`executionId` and no script, all of which its own pages and the DFG-Viewer
use:

- `queryItemSignatureSuggestions` is the signature form's autocompleter: given
  the archive's id (HStAM is 84, HHStAW 47, HStAD 1), a fonds and a number
  prefix it answers JSON with each unit's id. The 0.2.0 attempt failed
  because the form's hidden archive id, which the autocompleter fills in,
  was empty.
- `mets?detailid=v<id>` is the METS file Arcinsys hands the DFG-Viewer: the
  unit's title and shelf mark, the owner, an empty licence field, and the
  page images in viewer order. An unknown or non-public unit redirects to
  `accessDeniedError.action`, which `hessen_image` reads as not found.
- The images are static JPEGs on `digitalisate-he.arcinsys.de`; each address
  redirects, on the same host, to its full-size copy under `max/` (about
  2,000 by 2,800 pixels, 0.2 to 0.4 MB). The redirect is followed.

So Playwright, which the brief allowed as an optional extra if the flow could
only be driven by running the site's script, was not needed, and nothing in
this server runs a site's script.

Finding a register is LAGIS's job, as the Hessisches Landesarchiv's own guide
says. Its Angular application calls a keyless JSON API on
`www.lagis-hessen.de`; the simple search
(`/de/api/gsearch/sn/hessische-geburten-ehe-sterberegister?suchbegriff=`)
matches every word against the register's title and the places of its
Standesamt district, so `Korbach Geburtsnebenregister 1880` finds one
register and a village finds its Standesamt's. It caps a page at 25 and
orders by relevance (a sort parameter is ignored), and offers no year range:
a year is one more word, which matches only a register whose title names
it. The extended search (`xsearch`) ignored its year fields and took up to 20
seconds, so it is not used. Each hit's signature (`HStAM Bestand 922 Nr.
6013`) is what `hessen_image` takes, through the autocompleter; LAGIS's
record route (`idrecng`) also names the Arcinsys id but took 11 seconds, so
it is not used either. LAGIS is slow and uneven (0.4 to 35 seconds; one
connection attempt timed out), so its requests get a 90-second read timeout
and its searches are held ten seconds apart.

`page` is the image's place in the METS file's physical order, as the viewer
shows it. Arcinsys leaves out pages still under a protection period, so an
image's file number can run ahead of its place; the citation gives the
image number and the file name.

## Which hosts a tool reaches

Eight, fixed in `client.ALLOWED_HOSTS`: the DDB's API, the Landesarchiv
Baden-Württemberg's `www2` host, the Archive in NRW portal, the Landesarchiv
NRW's image server, APERTUS, LAGIS's API host, Arcinsys Hessen and its image
server. Nothing a model writes and nothing a site answers can add a ninth. That matters here more than for some sibling
servers, because DDB records and NRW hits carry image and viewer links to
hundreds of other institutions' servers: those are returned as data and
never requested. An NRW or Arcinsys METS file's image addresses are fetched
only if they are JPEGs on that archive's image server, and an APERTUS volume
only by the `/Bild/` path of the archive's file-name shape that the unit's
description named. The public permalink host
(`www.landesarchiv-bw.de`) is not needed, since it only redirects to `www2`;
it appears in citations, not in requests.

Behind the allowlist, every connection is checked where it is made: the
transport resolves the host itself, refuses it if any address is not public,
and connects to the address it checked, so redirects and DNS rebinding are
covered. The permalink service's redirects are read as answers and never
followed.

## What the image tools write

The four image tools are the tools that touch the local disk, so their
destination is held to what a page image needs and nothing that runs later
can use. They share one set of rules (`server._destination`). `rlp_image`
also writes volume PDFs, but only inside the cache folder, under file names
made from the unit's GUID after it has matched the GUID pattern. The
file must end in `.jpg` or `.jpeg` before anything is fetched, and the bytes
must be a JPEG by their first bytes, never by the Content-Type. Where it
lands is checked after links are resolved, and folders are compared by
identity, so neither a link nor a case-insensitive disk slips one past:

- **No hidden component.** No dotfile, nothing in `.ssh`, `.config` or
  `.git/hooks`.
- **Nothing under `~/Library`,** where launch agents and login items live.
- **Inside `GERMAN_ARCHIVES_DOWNLOAD_DIR`, when it is set.** The operator's
  folder may itself be hidden or under `~/Library`; an iCloud Drive folder is
  under `~/Library/Mobile Documents`, and this is how to save there. What a
  model adds below the folder is held to the rules above.

The file is created exclusively, so nothing is overwritten (a dangling link
included), and a refused download leaves nothing on disk. These rules are
the same as the sibling servers'.

## The evidence model

- **A finding-aid entry is not the record.** Every DDB answer that carries
  archival entries says so, and the server's instructions say it again.
- **Cite the archive.** `ddb_item`'s citation names the holder, its
  signature, the title and dates, and the archive's own page when the record
  names one, falling back to Archivportal-D. The DDB id is a finder: it
  changes when an archive re-delivers its finding aid.
- **The page is the evidence.** `labw_image`'s citation follows the archive's
  form ("Landesarchiv Baden-Württemberg, Abt. Staatsarchiv Freiburg, L 10 Nr.
  510, Bild 378") with the image's permalink, which the archive's terms ask
  every user to cite. `nrw_image`'s names the department, the signature and
  the image ("Landesarchiv NRW Abteilung Rheinland, PA 2104 Nr. 267, Bild
  12") with the permalink and the URN, which the Landesarchiv NRW's terms ask
  for. `rlp_image`'s names the holder, the signature, the title and years and
  the PDF page ("Landesarchivverwaltung Rheinland-Pfalz, Landeshauptarchiv
  Koblenz, Best. 657,349 Nr. 4 (...), PDF page 3"), the short form "LHA Ko
  Best. 657,349 Nr. 4", and the permalink; the archive asks that published
  sources be cited. `hessen_image`'s names the department, the signature, the
  title and the image ("Hessisches Staatsarchiv Marburg, HStAM 922 Nr. 6013
  (...), Bild 2"), the file name and the Arcinsys permalink.
- **A zero is bounded.** A DDB search that finds nothing says it covers only
  what archives delivered, and only their descriptions. A Standesbuch search
  that finds nothing names the reasons: spelling, a place outside
  Baden-Württemberg, a year outside the registers. An NRW search that finds
  nothing says the portal searches descriptions, filed by Standesamt; an
  APERTUS search, that units are filed by Bürgermeisterei and that the
  Palatinate and Rheinhessen are mostly not there; a LAGIS search, that a
  year must be in the title and which years are online.
- **Outages are not zeros.** A site that does not answer is
  `upstream_error`, `timed_out` or `rate_limited`, each saying it is not an
  empty result; a book list survives the Landesarchiv failing, with its image
  counts left empty and a note.

## Courtesy

The client sends one request at a time per host, never less than two seconds
apart whatever the setting, and the Archive in NRW portal's, APERTUS's and
LAGIS's searches never less than ten seconds apart, because they run on the
archive's own database (`client.SEARCH_FLOORS`; APERTUS's took up to 8
seconds, LAGIS's up to 35). Opening an APERTUS unit, which makes the archive
build a volume's PDF that is then downloaded, is held ten seconds from the
last (`client.VOLUME_FLOORS`), and each volume is downloaded once per
`GERMAN_ARCHIVES_PDF_CACHE_DAYS`. The DDB's search is a public Solr index built for
programmatic use, answering in under two seconds, and keeps the two-second
floor. Identical calls in flight are joined. DDB and NRW searches are cached
for a day, DDB records and register searches for a week, and a book's
signature lookup, the Landesarchiv's permalink answers, its image lists and
the Landesarchiv NRW's METS files for 30 days. Images are written to the caller's file and
never cached. A 429, a 5xx or a dropped connection gets one retry, honouring
`Retry-After` up to 30 seconds; a timeout gets none. The User-Agent names the
package, its version and this repository, and `GERMAN_ARCHIVES_CONTACT` adds
the operator's address. A DDB search asks for at most 50 hits: the API itself
sets no ceiling, and will send tens of megabytes if asked.

## Out of scope, by decision

- **Writing to a site.** The client sends GET requests to search and read,
  and posts APERTUS's search and unit-description forms, which are how that
  site reads; the DDB's account, favourites and saved-search routes and every
  account, basket and order route of APERTUS and Arcinsys are never called.
- **Working around bot checks.** An Anubis, Cloudflare or Imperva page is
  reported as `blocked`. The DDB's portal is behind Anubis; the server never
  calls it. The User-Agent is always the server's own; no browser is
  imitated and no header is forged.
- **Running a site's script.** No browser and no Playwright: every route
  used answers plain HTTP.
- **Resizing pages.** `rlp_image` and `hessen_image` save the archive's JPEG
  unchanged.
- **The DDB's version 1 API.** It needs a key, and the DDB no longer issues
  new ones.
- **Images on other institutions' servers.** `ddb_item` and `nrw_search`
  return their links; fetching them would mean an open-ended host list.
- **Transcription.** The registers are handwritten, mostly in German script;
  the image is returned to be read.
- **Bulk harvesting.** The DDB offers OAI-PMH for that; this server reads
  entries one at a time for research.

## Other state archives

Surveyed on 2026-10-11 for 0.2.0, revisited for 0.3.0. The rule: an archive is
added if its registers are reachable over plain HTTP, its terms allow it, and
no bot check stands in front. `robots.txt` is recorded as a fact, not a
verdict.

- **Rheinland-Pfalz (APERTUS).** Added in 0.3.0; see above. The 0.2.0 survey
  thought a cookie session was needed; the unit search and description
  answered without one.
- **Hesse (LAGIS and Arcinsys).** Added in 0.3.0; see above. The 0.2.0
  survey's session problem was the signature form's empty hidden archive id;
  the autocompleter, the METS route and the image server need no session.
- **Berlin.** The Landesarchiv Berlin's civil registers (P Rep., 1874-) are
  described on findbuch.net and in the DDB; the images are on Ancestry,
  which charges. Not added.
- **Saarland.** No civil registers online at the Landesarchiv Saarland.
- **Bavaria.** Civil registers stay with the municipalities; church books
  are with the dioceses (several on Matricula) and the Lutheran church
  (Archion). The Palatinate's registers belong to Rheinland-Pfalz.
- **Thuringia and Saxony.** No state collection of registers online; church
  books and their duplicates are on Archion, which charges.
- **Also found, through the DDB:** the Niedersächsisches Landesarchiv
  (French-period civil registers, Osnabrück, in Arcinsys Niedersachsen), the
  Brandenburgisches Landeshauptarchiv (church-book duplicates, Rep. 5KB) and
  the Geheimes Staatsarchiv (duplicates of East Prussian church books, VIII.
  HA EKB) deliver digitised registers to the DDB; `ddb_search` finds them and
  `ddb_item` returns their image links.

**Matricula** (`data.matricula-online.eu`) holds church books of dioceses in
Germany, Austria, Poland and beyond. Its catalogue is plain HTML, but its
image host answered a scripted request with 403, and its images are CC
BY-NC-ND. If it is served, it deserves a server of its own, built with the
operator's agreement, rather than a pair here (see docs/API-NOTES.md).

## Tests

- Everything is mocked with respx against **recorded** responses
  (`tests/fixtures/`): registers and finding-aid headings from the Stadtarchiv
  Düsseldorf, the Breisach books of L 10 and J 386, the Ulm books of every
  fonds, the Landesarchiv NRW's Barmen and Lemgo registers, APERTUS's Cochem,
  Münstermaifeld and St. Johann (near Mayen) registers with a three-page cut
  of a volume PDF, and LAGIS's and Arcinsys's Korbach registers. The suite
  never touches a live site.
- Contract tests pin the tool surface as a client sees it: names and
  parameters (snapshot), descriptions present, dedented and within a size
  budget, the pitfalls present in the descriptions, annotations, no tool that
  raises when both sites fail, unknown parameters refused.
- `tests/test_security.py` takes the attacker's side: a host off the list, an
  image link in a record, a hostile permalink redirect, a name that leads to
  a private address, a rebinding name, an answer too large, a destination
  that would run later. Each refusal is checked to come before the harm, and
  each allowed path is checked to still work.
- `tests/live_check.py` checks the answers the server was built against, by
  hand.
