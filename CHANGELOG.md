# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). The tool surface is the public
interface: renaming or removing a tool or a parameter is a major release, and
adding one is a minor release. Before 1.0, a minor release may do either.

## [Unreleased]

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
