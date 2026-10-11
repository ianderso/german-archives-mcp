# API notes

What the two sites actually do, observed on 2026-10-11 from a US address
with this package's User-Agent, about 90 requests in all, paced at least 2.5
seconds apart while probing. Labels: **[live]** fetched that day; **[docs]**
the provider's own documentation.

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
- The Standesbücher viewer, in both fonds, links the Public Domain Mark 1.0
  (`rechtekategorie1`) **[live]**.
- `robots.txt` on `www2.landesarchiv-bw.de`: `Allow: /` for Googlebot and
  Yahoo, `Disallow: /` for everyone else. On `www.landesarchiv-bw.de`: only
  `/sixcms/admin` disallowed **[live]**. Reported as facts.
- No bot check met. Pages took 0.4 to 2 s.

### Fonds

| Fonds | Archive | OLF `bestand` | `scopeid_besta` | Permalink prefix | Region |
| --- | --- | --- | --- | --- | --- |
| L 10 Standesbücher | Staatsarchiv Freiburg (`archiv_5`) | 10028 | 5698 | `5-` | south Baden: 35 district courts |
| 390 Standesbücher | Generallandesarchiv Karlsruhe (`archiv_4`) | 12390 | 5405 | `4-` | north Baden |

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
