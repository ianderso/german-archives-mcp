# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately, through GitHub's
[private vulnerability reporting](https://github.com/ianderso/german-archives-mcp/security/advisories/new)
(the **Report a vulnerability** button on the repository's Security tab), not
in a public issue. Include what an attacker controls, what they gain, and the
steps to reproduce it.

You should hear back within a week. Fixes are released for the latest version
only.

## Scope

In scope: this server — the requests it makes, the files it writes (its cache
and the images `labw_image` saves), and anything a tool argument or a site's
response can make it do.

Out of scope: the Deutsche Digitale Bibliothek, the Landesarchiv
Baden-Württemberg and the archives whose finding aids they publish, which
this project does not operate. Report problems with those to them.

## The security model, briefly

- **No credentials.** The DDB's version 2 API and the Landesarchiv's online
  finding aids need none. The server holds no key and sends none.
- **Tool arguments are treated as the attacker's.** A model writes them, and
  the model reads finding-aid text, image links and web pages that may carry
  injected instructions. Everything below is about what such an argument can
  make the server do.
- **A fixed allowlist of two hosts.** `api.deutsche-digitale-bibliothek.de`
  and `www2.landesarchiv-bw.de`. A request to any other host, or over plain
  http, is refused before it is resolved, so not even a DNS query carries a
  name an attacker chose. That holds for addresses taken from responses: the
  image links in a DDB record are returned as data and never requested, and
  the Landesarchiv's permalink redirects are read, never followed.
- **Public addresses only, checked at connect time.** The transport resolves
  each host itself, refuses the connection if any address is private,
  loopback, link-local, shared (CGNAT), multicast, reserved, unspecified or
  site-local, in IPv4 or IPv6 (an IPv4-mapped, 6to4 or NAT64 address is judged
  by the IPv4 address inside it), and connects to the address it checked. A
  redirect or a retry is a new connection, checked again, so DNS rebinding
  gains nothing. Proxy settings in the environment are not used.
- **Redirects are followed by hand,** and only within one host. A redirect
  anywhere else is reported to the caller and not followed.
- **Bounded answers.** A JSON or HTML answer over 10 MB or an image over 60 MB
  is refused as it streams in, whether or not its size was declared. A
  search asks for at most 50 hits.
- **Read-only calls.** The client sends GET requests to the DDB's search and
  item routes and to the Landesarchiv's permalink, image-list and image
  scripts. The DDB's account, favourites and saved-search routes are never
  called.
- **Arguments are validated** before they are placed in a request. Search
  words have Solr's syntax characters (`\ : / [ ] { } ^ ~ !`) escaped, so no
  field, range, local parameter or regular expression reaches the index; a
  holder's name is escaped character by character as a literal; a place must
  be letters, spaces and a few punctuation marks; a DDB id must be 32
  base32 characters; a signature or permalink must match a narrow pattern;
  and an image file name must come from the archive's own list and have the
  archive's file-name shape, so no path can be smuggled into the image
  script's parameter.
- **Local writes.** The cache lives under `GERMAN_ARCHIVES_CACHE_DIR`, in
  files named by a hash of the request address and written atomically.
  `labw_image` writes only the absolute path it is given, and only if that
  path, with its links resolved, ends in `.jpg` or `.jpeg`, has no hidden
  component, is not under `~/Library`, and lies inside
  `GERMAN_ARCHIVES_DOWNLOAD_DIR` when that is set (the operator's folder may
  itself be hidden or under `~/Library`; what a model adds below it may not).
  The bytes must be a JPEG by their first bytes. The file is created
  exclusively (an existing file or link is never overwritten or followed) and
  removed if writing fails; a refused download writes nothing at all.
- **Site responses carry untrusted text.** Titles and descriptions are
  written by archivists and reach the model verbatim, which makes them a
  channel for prompt injection. The server's instructions tell the model to
  treat that text as material, not as instructions, but the model still
  decides what to do next. An injection that leads the model to misuse this
  server's own tools is in scope; one that leads it to misuse other tools the
  client has connected is a client concern.
- **`GERMAN_ARCHIVES_CONTACT` is checked** for newlines and parentheses before
  it is placed in the User-Agent header.
