# Design

Why the server is shaped the way it is, and what is out of scope by decision.

## The questions it answers

"Which German archive holds a record of this place, and under what
signature?" and "Is the Baden register for this parish and year online, and
what does the page say?"

German archival records are scattered across thousands of state, municipal,
and private archives, few of which put registers online. Many deliver
their finding aids to the Deutsche Digitale Bibliothek, which shows them in
Archivportal-D and serves them through one keyless API: that is the nearest
thing Germany has to a union catalogue of archives, and the core of this
server. In Baden, one set of registers is online in full: the Standesbücher,
the civil duplicates of the parish registers for 1810 to 1870, at the
Landesarchiv Baden-Württemberg. That is the second half.

## Two sources, five tools

- `ddb_search` and `ddb_item` are the DDB half, shaped like
  [dpla-catalog-mcp](https://github.com/ianderso/dpla-catalog-mcp)'s
  `search_items` and `get_item`: a search that returns citable hits, and a
  record read in full. A DDB archival entry also sits in a hierarchy (archive,
  holdings overview, fonds, series, unit), which DPLA records do not, so
  `ddb_item` returns the path down to the entry and, for a fonds or a series,
  what lies below it. That is how a finding aid is browsed.
- `labw_standesbuch` and `labw_image` are the Landesarchiv half: find the
  book, then read one page of it.
- `cache_status` is the house tool for what a session has asked of each
  host.

The tool count stays small on purpose: the descriptions are sent on every
session, and a model chooses better among five tools than among fifteen.

## Finding a Standesbuch through the DDB

The Landesarchiv's online finding aids (OLF) offer a structure view by
district court and a search form, but no API. Its finding aid for L 10 and
390 is also delivered to the DDB, under CC0, with each book's signature,
title, years, district court and a `provider_item_id` (`labw-5-475861`) that
is the Landesarchiv's own scope id, from which the permalink follows. So
`labw_standesbuch` asks the DDB one question (books in the two fonds whose
title names the place, overlapping the year) and asks the Landesarchiv only
for the image counts of the first four books. The alternative, walking the
structure view by district court, would mean several requests to a site
whose `robots.txt` asks scripts to stay away, and a place-to-court table to
maintain.

The title search is a phrase search on the title field. A village
incorporated into a town carries both names (`Niederrimsingen, Breisach am
Rhein FR`), so a search for the town lists its villages, and
`place_named_first` tells them apart. Confession is read from the title,
where the archive writes it.

## Reading a page

`labw_image` uses the three steps the archive's own viewer uses: the
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

## Which hosts a tool reaches

Two, fixed in `client.ALLOWED_HOSTS`: the DDB's API and the Landesarchiv's
`www2` host. Nothing a model writes and nothing a site answers can add a
third. That matters here more than for some sibling servers, because DDB
records carry image links to hundreds of other institutions' servers: those
are returned as data and never requested. The public permalink host
(`www.landesarchiv-bw.de`) is not needed, since it only redirects to `www2`;
it appears in citations, not in requests.

Behind the allowlist, every connection is checked where it is made: the
transport resolves the host itself, refuses it if any address is not public,
and connects to the address it checked, so redirects and DNS rebinding are
covered. The permalink service's redirects are read as answers and never
followed.

## What labw_image writes

`labw_image` is the one tool that touches the local disk, so its destination
is held to what a page image needs and nothing that runs later can use. The
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
  every user to cite.
- **A zero is bounded.** A DDB search that finds nothing says it covers only
  what archives delivered, and only their descriptions. A Standesbuch search
  that finds nothing names the reasons: spelling, a place outside Baden, a
  year outside 1810-1870.
- **Outages are not zeros.** A site that does not answer is
  `upstream_error`, `timed_out` or `rate_limited`, each saying it is not an
  empty result; a book list survives the Landesarchiv failing, with its image
  counts left empty and a note.

## Courtesy

The client sends one request at a time per host: the DDB's at least a second
apart (configurable, never below half a second), the Landesarchiv's never
less than two seconds whatever the setting. Identical calls in flight are
joined. DDB searches are cached for a day, DDB records and Standesbuch
searches for a week, and a book's signature lookup, the Landesarchiv's
permalink answers and its image lists for 30 days. Images are written to the caller's file and
never cached. A 429, a 5xx or a dropped connection gets one retry, honouring
`Retry-After` up to 30 seconds; a timeout gets none. The User-Agent names the
package, its version and this repository, and `GERMAN_ARCHIVES_CONTACT` adds
the operator's address. A DDB search asks for at most 50 hits: the API itself
sets no ceiling, and will send tens of megabytes if asked.

## Out of scope, by decision

- **Writing to a site.** The client sends GET requests to search and read;
  the DDB's account, favourites and saved-search routes are never called.
- **Working around bot checks.** An Anubis or Cloudflare page is reported as
  `blocked`. The DDB's portal is behind Anubis; the server never calls it.
- **The DDB's version 1 API.** It needs a key, and the DDB no longer issues
  new ones.
- **Images on other institutions' servers.** `ddb_item` returns their links;
  fetching them would mean an open-ended host list.
- **Transcription.** The Standesbücher are handwritten in German script; the
  image is returned to be read.
- **Bulk harvesting.** The DDB offers OAI-PMH for that; this server reads
  entries one at a time for research.

## Tests

- Everything is mocked with respx against **recorded** responses
  (`tests/fixtures/`): registers and finding-aid headings from the Stadtarchiv
  Düsseldorf and the Breisach books of L 10. The suite never touches a live
  site.
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
