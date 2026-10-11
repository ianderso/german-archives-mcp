# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). The tool surface is the public
interface: renaming or removing a tool or a parameter is a major release, and
adding one is a minor release. Before 1.0, a minor release may do either.

## [Unreleased]

## [0.2.0] — 2026-10-11

Every register fonds the Landesarchiv Baden-Württemberg has online, and the
Landesarchiv Nordrhein-Westfalen's civil registers.

### Added

- `labw_standesbuch` and `labw_image` cover every fonds of vital registers in
  the Landesarchiv Baden-Württemberg's online finding aids, not only Baden's
  Standesbücher: F 901 (Staatsarchiv Ludwigsburg, Württemberg's Catholic
  church-book duplicates, 1808-1875), Wü 110 T 1 (Staatsarchiv Sigmaringen,
  the Protestant duplicates of Württemberg and Hohenzollern, 1808-1875),
  J 386 (Hauptstaatsarchiv Stuttgart, the films of the Jewish communities'
  registers) and Dep. 1 T 37 and T 44 (Staatsarchiv Sigmaringen, the civil
  registers of Sigmaringen and Sigmaringen-Laiz to 1899), beside L 10 and
  390.
- `labw_standesbuch` takes `fonds` to search one of them, finds Württemberg
  volumes by the parish heading above them, and returns each book's `fonds`,
  `place`, `registers` and `has_images`. Only books with images are counted.
- `labw_image` takes the signatures of every fonds (`F 901 Bd 1511`,
  `Wü 110 T 1 Nr. 4566`, `J 386 Bü 583`, `Dep. 1 T 37 Nr. 4`), with or
  without the department.
- `nrw_search`: the Archive in NRW portal's keyless search, with filters for
  the Landesarchiv NRW's departments, years and digitised units; each hit
  names the archive, signature, dates, fonds and permalink, and for a
  digitised unit its METS address.
- `nrw_image`: one page of a Landesarchiv NRW unit, by its METS address, a
  DFG-Viewer link or the path below `/digitalisate/`, saved as a new `.jpg`
  under the same rules as `labw_image`, cited with the signature, the
  permalink and the URN.
- `cache_status` reports the seconds between database searches.

### Changed

- Every host is asked at most once in two seconds (the DDB's API included,
  which was once a second), and the Archive in NRW portal's searches at most
  once in ten. `GERMAN_ARCHIVES_MIN_INTERVAL` defaults to 2 and may not be set
  lower.
- The allowlist has four hosts: `www.archive.nrw.de` and
  `www.landesarchiv-nrw.de` join the DDB's API and the Landesarchiv
  Baden-Württemberg's finding aids.
- `labw_standesbuch` leaves out fonds and series headings, and lists the
  place's own books first, then by fonds, place and year.

## [0.1.0] — 2026-10-11

First release.

### Added

- Five tools: `ddb_search` and `ddb_item` over the Deutsche Digitale
  Bibliothek's keyless version 2 API (finding aids from Archivportal-D and
  digitised objects); `labw_standesbuch` and `labw_image` over the Baden
  Standesbücher at the Landesarchiv Baden-Württemberg, fonds L 10
  (Staatsarchiv Freiburg) and 390 (Generallandesarchiv Karlsruhe); and
  `cache_status`.
- `ddb_search` with filters for sector, the holder's name, images only and
  years (by overlap); every hit names the holder, signature, dates and its
  place in the fonds.
- `ddb_item` with every field the archive delivered, the path from the
  archive down through the fonds, the entries below a fonds or series, image
  links, rights, and a citation naming the archive, signature and the
  archive's own page. A series heading with no record of its own still
  answers with its hierarchy and children.
- `labw_standesbuch`: the books for a place, a year and a confession, with
  signature, years, district court, permalink and image count; villages
  filed under their present municipality are included and marked.
- `labw_image`: one page image by signature or permalink, at the archive's
  full viewer size or fitted to `max_pixels`, saved as a new `.jpg` (never a
  hidden file, never under `~/Library`, only inside
  `GERMAN_ARCHIVES_DOWNLOAD_DIR` when set), with a citation in the archive's
  form and the image's permalink. Image numbers are mapped through the
  archive's own image list, so a book whose permalinks fall out of step with
  its image numbers is read correctly.
- A fixed allowlist of two hosts, a public-address check at connect time,
  size caps as answers stream, one request at a time per host (the
  Landesarchiv's at least two seconds apart), a disk cache, one retry on 429
  and 5xx honouring `Retry-After`, and bot checks reported as `blocked`.
