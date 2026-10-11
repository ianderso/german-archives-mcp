# API notes

What the sites actually do, observed on 2026-10-11 from a US address with
this package's User-Agent: about 90 requests for 0.1.0, paced at least 2.5
seconds apart, and about 120 more for 0.2.0, at least 2 seconds apart per
host and 10 seconds apart for database searches. Labels: **[live]** fetched
that day; **[docs]** the provider's own documentation.

## Deutsche Digitale Bibliothek, version 2 API

### Access and terms

- Base `https://api.deutsche-digitale-bibliothek.de/2`. No key, no account,
  no cookie needed for search or items **[live]**. Answers carry
  `Access-Control-Allow-Origin: *` and set an F5 cookie (`TS0154…`) that
  nothing requires.
- The DDB's developer wiki: version 2 "endpoints are usable without an API
  key"; version 1 may need one and new keys are no longer issued
  (*Differences between API versions 1 and 2*, updated 2025-06-05); and the
  API and its data are publicly accessible without restriction (*DDB-Backend
  / API*) **[docs]**. The wiki moved to
  `deutsche-digitale-bibliothek.atlassian.net/wiki/spaces/DDBDOK/`; the old
  `wiki.deutsche-digitale-bibliothek.de/x/…` short links redirect to its
  front page and lose the target.
- The OpenAPI description (`/2/q/openapi`, YAML, OpenAPI 3.0.3) declares
  bearer-token security only on the user, favourites and saved-search routes;
  search and items declare none. Its general description still says a key is
  required (text carried over from version 1), and says all metadata is CC0
  while binaries carry each institution's licence **[docs]**.
- DDBpro's *Schnittstellen* page still says an API key is needed **[docs]**.
  The version 1 route (`/items/{id}/view`) answers 403
  `NotAuthorizedException` without one **[live]**.
- The former API terms page, `www.deutsche-digitale-bibliothek.de/content/terms/api`,
  301s to `/content/api-nutzungsbedingungen`, which is a 404 **[live]**. The
  portal (`www.`) answers scripts with an Anubis proof-of-work page; it was
  read in a browser, and the server never calls it.
- No rate limit is documented or was met. Searches took 0.4 to 1.7 s; one
  facet count over all 64 million records took 12 s.
- `robots.txt` on the API host: 404 **[live]**.

### Search: `/2/search/index/search/select`

Apache Solr's select handler, passed through.

- `q` defaults to AND between words (`Standesamt Freiburg` 66 hits;
  `Standesamt OR Freiburg` 1.9 million). Quotes make phrases. An unbalanced
  parenthesis is tolerated, not refused.
- Fielded queries work in `q`: `title:"Breisach"` matches the title only,
  where plain `Breisach` also matches every book filed under the Breisach
  district court (23 against 4 for 1850).
- `fq` may repeat. `provider_fct` (a string field, case-sensitive) matches an
  exact holder name or a prefix with a trailing `*`
  (`provider_fct:Stadtarchiv\ Freiburg*`); a leading `*` matches nothing;
  `provider:` matches nothing.
- `sector_fct`: `sec_01` archive, `sec_02` library, `sec_03` monument
  preservation, `sec_04` research, `sec_05` media library, `sec_06` museum,
  `sec_07` other (checked by sampling holders). 37 of 64 million records are
  archival.
- `digitalisat:true` keeps records with images.
- `begin_time` and `end_time` are day counts: Python's `date.toordinal()`
  plus one (1847-01-01 is 674239). Range filters work.
- `fl`, `start`, `rows`, `sort` (`begin_time asc`) and `facet` work.
  **`rows` has no server-side ceiling**: a probe with `rows=100000` streamed
  over 40 MB before it was stopped. The server asks for at most 50.
- Response: `{"responseHeader", "response": {"numFound", "start", "docs"}}`.
  Fields the server reads: `id` (32 base32 characters), `title`,
  `dataprovider_fct` (the holder; `provider` may add an aggregator such as
  "Archive in NRW" or a parent body, in no fixed order),
  `apd_reference_number` (the signature, for Landesarchiv entries with the
  department: `Abt. Staatsarchiv Freiburg, L 10 Nr. 510`), `apd_context` (the
  path within the fonds: `Standesbücher >> Breisach; Amtsgericht`),
  `apd_level_of_description` (`htype_030` fonds, `htype_031` series,
  `htype_034` unit, `htype_037` a group in the holdings overview),
  `objecttype`, `sector_fct`, and `provider_item_id`, which for the
  Landesarchiv is `labw-<archive>-<scope id>`, the key of its permalink.
- `apd_reference_number:"Staatsarchiv Freiburg, L 10"` finds 3,323 entries;
  `"Generallandesarchiv Karlsruhe, 390"` 2,979. The phrase match does not
  confuse `L 10` with `L 100`, or `Nr. 51` with `Nr. 510`.

### Items

- `/2/items/{id}`: the whole record, 16 to 120 KB of JSON. The server reads
  `view.item` (title, institution, `origin` = the holder's own page,
  `license`, `rights`, and `fields`, a list of display fields with German
  labels such as `Archivaliensignatur`, `Bestand`, `Kontext`, `Laufzeit`,
  `Umfang`), `edm.RDF.ProvidedCHO` (identifier, date, `hierarchyType`),
  `provider-info` (ISIL, domains: `sparte001` is an archive) and
  `binaries.binary` (image links: `local_pathname`, `position`, `mimetype`,
  `kind` = licence).
- An unknown id: 404 `{"message": "No data row is available (size=0)."}`.
- **A grouping node** (a series heading such as `7-0-7-9.0000 Standesamt
  Oberkassel`, `aggregationEntity: true`) has no record: `/items/{id}` is
  404, while `/parents` and `/children` answer for it.
- `/2/items/{id}/parents`: the entry itself first, then each ancestor up to
  the institution, with `label`, `type`, `leaf`, `aggregationEntity` and
  `position`. An unknown id gives `{"numberOfResults": 0, "hierarchy": []}`.
- `/2/items/{id}/children?offset=&rows=`: what lies directly below, with
  `numberOfResults`. Rows come in no stable order (positions 01145, 01126,
  01118 in one answer); `position` is the finding aid's own order, and the
  server sorts each page by it. The default `rows=-1` returns everything.
- `/2/items/{id}/iiif`: 404 for the archival records tried (Landesarchiv and
  Bautzen); not used.
- Image links point at the holder's own server (`www.duesseldorf.de`,
  `archivverbund-bautzen.findbuch.net`). For Landesarchiv books the DDB lists
  only images 1 to 10, from a static export folder
  (`www2.landesarchiv-bw.de/exporte/digitalisate/…`); image 11 onwards is not
  exported (404), and the licence there is given as CC BY 3.0 DE, where the
  archive's own viewer shows the Public Domain Mark.

## Landesarchiv Baden-Württemberg, online finding aids (OLF)

### Terms

- *Nutzungsbedingungen auf einen Blick*
  (`/de/recherche/rechtsgrundlagen---nutzungsbedingungen/auf-einen-blick`,
  redirecting to `…/46047`): use of the online finding aids is free; their
  metadata is CC0; rights for each digitised item are shown at the item
  (Public Domain Mark, CC BY, Copyright Undetermined, Other Legal
  Restrictions); every user must cite the signature or the permalink; a
  deposit copy is due for a book that makes substantial use of the archive's
  material (§ 8 Abs. 9 LArchG). Nothing on automated access **[docs]**.
- The viewer links the Public Domain Mark 1.0 (`rechtekategorie1`, "Es ist
  gemeinfrei") for every fonds in the table, checked on one book each
  **[live]**.
- `robots.txt` on `www2.landesarchiv-bw.de`: `Allow: /` for Googlebot and
  Yahoo, `Disallow: /` for everyone else. On `www.landesarchiv-bw.de`: only
  `/sixcms/admin` disallowed **[live]**. Reported as facts.
- No bot check met. Pages took 0.4 to 2 s.

### Fonds

Found by asking the DDB for the Landesarchiv's fonds-level entries whose
titles name registers, then counting each fonds' entries with images
**[live]**:

| Fonds | Archive | OLF `bestand` | `scopeid_besta` | Permalink prefix | Unit word | Entries (with images) | What |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L 10 Standesbücher | Staatsarchiv Freiburg (`archiv_5`) | 10028 | 5698 | `5-` | Nr. | 3,323 | south Baden: 35 district courts |
| 390 Standesbücher | Generallandesarchiv Karlsruhe (`archiv_4`) | 12390 | 5405 | `4-` | Nr. | 2,979 | north Baden |
| F 901 Katholische Kirchenbücher: Zweitschriften | Staatsarchiv Ludwigsburg (`archiv_2`) | 18750 | 3493 | `2-` | Bd | 1,798 (1,796) | Württemberg's Catholic parishes, 1808-1875 |
| Wü 110 T 1 Evangelische Pfarrämter: Zweitschriften | Staatsarchiv Sigmaringen (`archiv_6`) | 54526 | 1496718 | `6-` | Nr. | 5,219 (5,189) | Württemberg's and Hohenzollern's Protestant parishes, 1808-1875 |
| J 386 Filme von Personenstandsregistern jüdischer Gemeinden | Hauptstaatsarchiv Stuttgart (`archiv_1`) | 5632 | 2764 | `1-` | Bü | 648 (606) | films of 1943-1945; originals lost |
| Dep. 1 T 37 Standesamt Sigmaringen | Staatsarchiv Sigmaringen | 23079 | 625516 | `6-` | Nr. | 105 (39) | civil registers, digitised 1870-1899 |
| Dep. 1 T 44 Standesamt Sigmaringen-Laiz | Staatsarchiv Sigmaringen | 24584 | 1344989 | `6-` | Nr. | 19 (7) | civil registers, digitised 1874-1899 |

- Wü 110 T 1 lists volumes that were never delivered with a placeholder for
  the number: `Abt. Staatsarchiv Sigmaringen, Wü 110 T 1 {1754: nicht
  vorhanden}`, with no images.
- J 386 entries carry further reference numbers after the signature
  (`RSA-Nr.: 3072`, `Mikrofilm-Nr.: HF 272, 279`); the signature comes first.
- The Staatsarchiv Wertheim's K-LRA 30 Personenstandszweitbücher (1870-2008,
  89.4 m) have no online finding aid: the permalink `7-4573` redirects to the
  holdings overview (`olb/struktur.php?archiv=7&...`), which says "Online-
  Findmittel im Intranet" **[live]**. None of its entries are in the DDB.
- No Catholic Hohenzollern duplicates were found in any fonds online; the
  Protestant ones are in Wü 110 T 1.
- Where the place is: in L 10, 390, J 386 and the deposits, the title; in
  F 901 and Wü 110 T 1, the last step of `apd_context`, numbered in F 901
  (`... >> 20. ORTSBUCHSTABE U >> 20.2 Ulm (St. Michael zu den Wengen)`) and
  not in Wü 110 T 1 (`... >> U >> Übr - Unl >> Ulm, Münster (Ulm UL)`).
- Place names repeat: a search for Ulm in 1850 finds 49 entries, from Ulm on
  the Danube (Wü 110 T 1, F 901, J 386) and from two Baden villages called
  Ulm (390 Nr. 923-925, Amtsgericht Bühl; L 10 Nr. 3639, Oberkirch).
- `-apd_level_of_description:(htype_030 OR htype_031 OR htype_037)` works as a
  filter query and leaves out the fonds and series headings.

### Permalinks

- `https://www.landesarchiv-bw.de/plink/?f=5-475861` 302s to
  `https://www2.landesarchiv-bw.de/ofs21/plink.php?f=5-475861`, which 302s
  to `olf/struktur.php?bestand=10028&sprungId=2239944&letztesLimit=suchen`
  (relative). `sprungId` is the book's OLF id, which the image list needs.
- `f=5-475861-377` 302s to
  `bild_zoom/plink_screen.php?bestand=10028&id=2239944&gewaehlteSeite=05_0000475861_0378_5-475861-377.png`:
  an image permalink ends in the last number of the image's file name.
- An image number the book does not have (`f=5-475861-999`) redirects to the
  book instead.
- An unknown item (`f=5-999999999`) answers 200 with a page saying "Zu dieser
  URL existiert <b>keine Ressource</b>".
- `plink_screen.php` is a stub that sends the browser on to `zoom.php`.

### The image list: `/ofs21/bild_zoom/thumbnails.php?bestand=…&id=…`

- About 60 KB of HTML. `<title>` is `Staatsarchiv Freiburg - Bestand L 10:
  Standesbücher - Dokumente - Auswahl`; `<div id="titelaufnahme">` holds
  `<b>Staatsarchiv Freiburg L 10 Nr. 510</b>` and the title; `<select
  name="gewaehlteSeite">` lists every image as `<option
  value="05_0000475861_0001_5-475861-1.png">Bild 1</option>`; thumbnail
  addresses carry `scopeid_besta`.
- File names: `<archive:2>_<scope:10>_<sequence:4>_<archive>-<scope>-<image
  id>.<png|jpg>`. The sequence and the image id usually agree, but not
  always: in L 10 Nr. 510 (380 images) the 119th entry is
  `05_0000475861_0119_5-475861-380.jpg`, an image added later, and every
  later image's id is one less than its place. GLA 390 files are `.jpg`.
- Counts seen: L 10 Nr. 469, 391 images; Nr. 481, 359; Nr. 510, 380; Nr. 517,
  359; GLA 390 Nr. 1875, 322.

### Images: `/ofs21/bild_zoom/bild.php`

- `?drehen=&zoom=100&gamma=1&jpegQualitaetZoombild=60&scopeid_besta=5698&originalBilddatei=/data/bildcms/internetbilder/archiv_5/olf/bestand_0000005698/titlaufn_0000475861/<file>`
  is what the viewer asks for. The answer is a JPEG made by gd.
- `zoom` scales linearly: 100 gave 2028 x 1520 for an L 10 spread, 50 gave
  1014 x 760, 150 gave 3042 x 2280 (upscaled; the viewer stops at 160). The
  added `.jpg` image rendered at about 1400 px wide at 100.
- `jpegQualitaetZoombild` sets the JPEG quality (60 in the viewer; the server
  asks for 85, about 0.9 MB for a spread).
- `/ofs21/bild_thumbnail/thumbnail.php?…&groesse=` is capped at 400 px.
- F 901's viewer (`zoom.php`) is an older one that crops through
  `bild2.php?…&groesse=6000&…&ausschnitt=…`, but the standard `bild.php`
  renders its files with the same path scheme: F 901 Bd 575, image 2, at zoom
  10 was 251 x 240, so about 2,500 x 2,400 at 100 **[live]**.
- File names follow the same scheme in every fonds
  (`02_0000181572_0001_2-181572-1.jpg`, `01_0000446805_0001_1-446805-1.png`,
  `06_0002785143_0001_6-2785143-1.jpg`). Image counts seen: F 901 Bd 1511,
  290; Wü 110 T 1 Nr. 4566, 294; J 386 Bü 583, 137; Dep. 1 T 37 Nr. 4, 419.
- The thumbnail page's `<title>` can carry markup: F 901's is `Staatsarchiv
  Ludwigsburg - Bestand F 901: Katholische Kirchenbücher: Zweitschriften
  <i>(Bitte Einführung beachten!)</i> - Dokumente - Auswahl`.

## Archive in NRW portal and Landesarchiv NRW

### Access and terms

- The portal (`www.archive.nrw.de`, Drupal 11) holds the finding aids of the
  Landesarchiv NRW and of some 400 archives in the state. Its search page
  (`/archivsuche`) is a script whose settings name three services:
  `base_url_search` `https://www.archive.nrw.de/sufservice`,
  `base_url_inventory` `.../bufservice`, `base_url_statistic` `.../statservice`
  **[live]**.
- `/sufservice/api/search` answers keyless JSON; no cookie or token is needed
  **[live]**. 0.5 to 1.6 s for a keyword search; 3.5 s for an empty search of
  all 9.8 million entries, which the server never sends.
- `/sufservice/api/listContextByNodeId?nodeId=VERZEICHUNGSEINHEIT-Vz_…`
  returns the whole tree of the unit's archive (306 KB, 4.2 s) **[live]**:
  too heavy to resolve a permalink with, and not used.
- Terms: the Landesarchiv's *Nutzungsbedingungen für Inhalte und Digitalisate*
  (`www.landesarchiv-nrw.de/digitalisate/LAV_NRW_Nutzungsbedingungen_Digitalisate.pdf`):
  finding aids CC0; digitised records CC BY-SA, free to download at the
  resolution provided; cite the signature, and online the permalink, for every
  image reused. Nothing on automated access **[docs]**.
- `robots.txt` on `www.archive.nrw.de`: Drupal's default (disallows `/core/`,
  `/profiles/`, `/admin/`, `/search/`, `/user/...` and the like); nothing on
  `/sufservice/` **[live]**. `www.landesarchiv-nrw.de/robots.txt`: 404
  **[live]**. No bot check met on either host.

### Search: `/sufservice/api/search`

- Parameters (from the page's script and tried **[live]**): `keyword`
  (words, all must match; they match titles, abstracts and the fonds' title:
  `Sterberegister Lemgo` finds registers of Standesämter in the fonds `P 3 /
  9 Lemgo - Landkreis`), `hasDigitalisat=true`, `archive` (the archive's
  number, its `mandant`: 185 Rheinland, 1 Westfalen, 10003
  Ostwestfalen-Lippe), `laufzeitVon` and `laufzeitBis` (years), `size`, and
  `page` (from 0). `link` is not a filter: with it alone the service returns
  everything.
- Response: `{"keyword", "hits", "pages", "filter": [facets by archivtype,
  archivname, findbuchid], "searchResult": [...]}`. Each result has `title`
  (matches wrapped in `<mark>`), `laufzeit`, `archivName`, `mandant`,
  `signatur` (`267`, `69 - Band: 1`), `bestandSignature` (`PA 2104`, `P 3 /
  9`), `bestandTitle`, `objectTyp`, `textAbstract`, `accessrestrict` (old
  protection notes such as `Für die Nutzung gesperrt bis 1841`), `permalink`
  (`https://www.archive.nrw.de/ms/search?link=VERZEICHUNGSEINHEIT-Vz_<id>`;
  some answers write `http://`) and `disitalisat` (sic), a list of DFG-Viewer
  links whose `tx_dlf[id]` is the METS address.
- `Sterberegister` with images: 82,845 entries, 44,541 in Ostwestfalen-Lippe
  and 35,772 in Rheinland **[live]**. `Geburtsregister Barmen` in Rheinland
  with images: 157; in 1850, 2.
- The DDB's facet over digitised register entries in archives (2026-10-11)
  puts the Landesarchiv NRW first (65,188 Ostwestfalen-Lippe, 9,567
  Rheinland), then the Landesarchiv Baden-Württemberg (13,764).

### METS files and images: `www.landesarchiv-nrw.de`

- METS at `/digitalisate/<department>/<fonds>/~<group>/<unit>/mets.xml`
  (`Abt_Rheinland/PA_2104/~002/00267`,
  `Abt_Ostwestfalen-Lippe/P3/P3-09/~002/P3-09_00260`), static, `Content-Type:
  application/xml`, `Access-Control-Allow-Origin: *`, with a byte-order mark
  **[live]**. 19 KB for 14 pages, 487 KB for 457, 899 KB for 827.
- File groups `DEFAULT` (the page JPEGs), `DOWNLOAD` (the same JPEGs and a
  ZIP of the volume at `/dwl?f=…`) and `THUMBS` (250 px wide). The physical
  structure map orders the pages (`ORDER="1"`…); the logical map has one
  entry, "(Abbildungen sind nicht weiter strukturiert)".
- MODS: `mods:title` `Abteilung Rheinland, PA 2104 (Zivilstandsregister
  Landgerichtsbezirk Elberfeld), Nr. 267`; `mods:identifier type="VERA
  dockey"` `Vz <id>` (the permalink's id); `type="urn"`
  `urn:nbn:de:danrw:de2189-<id><check digit>`; `mods:accessCondition`
  `CC-BY-SA` with `href` to the CC BY-SA 4.0 deed. `dv:owner` `Landesarchiv
  NRW`.
- Images at `/data01/…` and `/data02/…`, `<prefix>_<unit>_<page>.jpg`: a
  Lemgo death-register page 1762 x 2605, 609 KB; Barmen pages 180 to 420 KB
  **[live]**. Other archives' METS files are on their own servers
  (`www.duesseldorf.de/stadtarchiv/archivenrw/…`).

## Surveyed and not added

### Landesarchiv Rheinland-Pfalz: APERTUS (`apertus.rlp.de`)

- A PHP application in iframes; a session cookie (`_ap_sid`) is set on the
  first page. No token is needed: with the cookie, `lha.php` (POST, the
  form) and `queryfacet.php` (POST: `query`, `archiv=PStA`, `doc=TRUE`,
  `rows`, …) answer the facet counts per fonds, and `queryOneExt.php` (POST,
  `bestand` sent URL-encoded inside the form value, `%22657%2C008%22`) lists
  units with their GUIDs **[live]**. Answers are HTML fragments.
- The Personenstandsarchiv's digitised units: `Geburtsregister` finds 18,491
  in 485 fonds (Best. 657,001 onward, one per Standesamt or
  Bürgermeisterei); `Koblenz` 485; `Alzey` 1 **[live]**. The Stadtbürgermeisterei
  Koblenz's registers (657,008) have only their name indexes digitised
  ("Digitalisat: Nur Namensverzeichnis").
- `vz_php.php` (POST, `GUID`) describes a unit and, as a side effect, builds
  `/Bild/PStA_<fonds>_<nr>.pdf`, which is gone a few minutes later (404
  before the unit is opened, 200 after, 404 again later) **[live]**. The PDF
  is Ghostscript's, PDF 1.4, pages as DCTDecode images: 6.1 MB and 8.0 MB for
  two ten-page indexes. A thumbnail of the first page is static
  (`/Bild/PV/PStA_<fonds>_<nr>_P1.jpg`, 514 x 702). The site's viewer script
  also asks `imgviewer.php` (POST) for single pages; neither unit opened used
  it.
- Permalinks: `https://apertus.rlp.de/index.php?PLINK=1&ID=<GUID>`.
- Terms: `Disclaimer.php` forbids unconstitutional, racist, defamatory or
  otherwise unlawful use; nothing on automated access **[live]**.
  `robots.txt`: 404. No bot check met.

### Hessisches Landesarchiv: Arcinsys and LAGIS

- LAGIS moved to `lagis.hessen.de` (an Angular application; `robots.txt`
  allows all user agents but a list of named crawlers). Its API on
  `www.lagis-hessen.de/de/api/…` answers keyless JSON:
  `/de/api/xsearch/sn/hessische-geburten-ehe-sterberegister` reports 118,206
  registers (`{"id": "365-2", "subTitle": "HHStAW Best. 365 Nr. 2", "title":
  "Personenstandsregister der Juden von Arolsen (1834-1842 ...)"}`)
  **[live]**. The free-text parameter was not found; `suchbegriff` was
  ignored.
- The images are in Arcinsys (`arcinsys.hessen.de/arcinsys/`), a
  Struts application with a session cookie and an `executionId` in each
  form; the signature search (`identifierSearch_search.action`, GET) with a
  cookie and the form's `executionId` redirected back to the empty form
  **[live]**. Its `robots.txt` names only a sitemap. The archive's guides say
  the registers are online to 1900 (births), 1930 (marriages) and 1965
  (deaths), in fonds 900-926 of the Hessisches Staatsarchiv Marburg
  **[docs]**. No licence statement for the images was found.

### Matricula (`data.matricula-online.eu`)

- Church books of dioceses and archives in Germany (24 sections, among them
  a Landesarchiv Baden-Württemberg and a Geheimes Staatsarchiv section),
  Austria, Poland, Serbia, Slovenia, Italy, Switzerland, Luxembourg and
  Bosnia. Country, diocese and parish pages are plain HTML
  (`/de/deutschland/passau/`, 290 parishes; `/de/deutschland/passau/<parish>/`,
  a table of registers with type and dates) **[live]**.
- A register page (`/de/deutschland/passau/<parish>/001_01/`) embeds its
  viewer's settings: `labels` (`001-01_0000`, ...), `files` (`/image/<base64
  of http://hosted-images.matricula-online.eu/images/matricula/...jpg>/`)
  and `path` `https://img.data.matricula-online.eu` **[live]**.
- `data.matricula-online.eu/image/<...>/` redirects to `/de/image/<...>/`,
  which answers 404; `img.data.matricula-online.eu/image/<...>/` answered
  **403** to a scripted request (`Vary: Origin`) **[live]**. Probing stopped
  there.
- Terms (`/de/nutzungsbedingungen/`): images CC BY-NC-ND 2.0, no commercial
  reuse; data only as each state's civil-status and data-protection law
  allows; tell the archive or diocese of any publication. Nothing on
  automated access **[live]**.
- `robots.txt` (served from `cdn-static.matricula-online.eu`): ClaudeBot,
  GPTBot, CCBot and other named crawlers `Disallow: /`; everyone else may not
  fetch `/*?pg=`, `/*/suchen`, the map features or accounts **[live]**.

### Others

- **Landesarchiv Berlin**: civil registers (P Rep., from 1874) described on
  findbuch.net and in the DDB; images on Ancestry **[docs]**.
- **Landesarchiv Saarland**: no civil registers online found **[docs]**.
- **Bavaria, Thuringia, Saxony**: no state collection of digitised registers;
  church books with the churches (Matricula, Archion) **[docs]**.
