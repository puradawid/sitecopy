# Architecture

`sitecopy` is a command-line website mirroring tool. It starts from one root
URL, crawls allowed pages and assets, writes them into a deterministic local
directory tree, rewrites downloaded references to local paths, validates the
result, and records crawl metadata in SQLite plus a JSON report.

The implementation is intentionally static. It fetches HTTP resources and
parses HTML/CSS that already exists in the response body. It does not run a
browser, execute JavaScript, submit forms, or reproduce backend behavior.

## Entry Points

The installed console script is defined in `pyproject.toml`:

```text
sitecopy = "sitecopy.cli:main"
```

`src/sitecopy/cli.py` exposes three commands:

- `sitecopy mirror <url>` loads configuration, creates a `Crawler`, runs the
  crawl, prints the summary report, and writes output files.
- `sitecopy init-config [path]` writes an editable default YAML configuration
  file and refuses to overwrite an existing file unless `--force` is passed.
- `sitecopy validate <output_dir>` checks local HTML/CSS references in an
  existing mirror.
- `sitecopy report <output_dir>` prints an existing `report.json`.

The CLI is thin by design. Most behavior lives in configuration loading,
crawling, URL policy, parsing, storage, path mapping, rewriting, validation,
and reporting modules.

## Configuration

`src/sitecopy/config.py` defines the `Config` dataclass and merges inputs from:

1. an optional YAML config file,
2. the positional root URL,
3. the CLI output directory flag,
4. explicit CLI overrides such as depth, page limit, dry-run mode, and logging.

Validation requires an absolute `http` or `https` `root_url`. If
`allowed_hosts` is omitted, it defaults to the root URL hostname.

Important configuration fields:

- `allowed_hosts` and `excluded_hosts` control host policy.
- `follow_subdomains` allows hosts below configured allowed hosts.
- `treat_http_https_as_same_host` controls whether `http` and `https` URLs
  share the same crawl identity.
- `max_depth`, `max_pages`, and `max_assets` limit crawl scope.
- `download_external_assets` allows assets from otherwise external hosts.
- `rewrite_mode` chooses relative or root-relative local links.
- `keep_query_string_variants` controls whether query strings affect identity
  and file names.
- `resume` skips previously downloaded resources found in `manifest.sqlite`.
- `update_mode` exists in configuration but is rejected by the CLI because it
  is not implemented in this version.

`concurrency`, `respect_robots_txt`, `asset_extensions_allowlist`, and
`canonicalization_rules` are accepted by configuration but are not currently
enforced by the crawler.

## Crawl Flow

`src/sitecopy/crawler.py` coordinates the mirror operation.

At startup, `Crawler` creates:

- a `Store` backed by `<output_dir>/manifest.sqlite`,
- a `PathMapper` for deterministic local file paths,
- a synchronous `Fetcher`,
- in-memory sets/maps for seen identities, downloaded bodies, and resource
  kinds.

The crawler performs a breadth-first crawl:

1. Canonicalize the configured root URL.
2. Enqueue the root page at depth `0`.
3. Pop queue items in order.
4. Skip already-seen canonical identities.
5. Apply depth/page/asset limits.
6. Apply URL policy.
7. Fetch the resource unless it is already present in the manifest and
   `resume` is enabled.
8. Classify the response as `page`, `css`, or `asset`.
9. Map the resource to a local path and write the response body.
10. Store resource metadata, redirects, skips, and collisions.
11. Discover child references from downloaded HTML or CSS.
12. Sort discovered children by canonical identity before enqueueing for
    deterministic traversal.
13. After the queue is empty, rewrite downloaded HTML/CSS references.
14. Validate the output tree.
15. Write `report.json`.

Requests are currently sequential even though `concurrency` is part of the
configuration shape.

## URL Identity

`src/sitecopy/canonicalize.py` converts raw URLs into `CanonicalURL` objects.
Canonicalization:

- resolves relative URLs against a base URL,
- accepts only `http` and `https`,
- lowercases hostnames and schemes,
- removes fragments,
- drops default ports,
- normalizes `.` and `..` path segments,
- percent-encodes paths consistently,
- optionally keeps or drops query strings,
- optionally collapses `http` and `https` into one logical identity.

Each canonical URL has both:

- `fetch_url`, the concrete URL used for HTTP requests,
- `identity`, the normalized key used for deduplication and manifest storage.

When `treat_http_https_as_same_host` is true, the identity scheme is `site`
instead of `http` or `https`, so mixed-protocol links deduplicate together.

## URL Policy

`src/sitecopy/policy.py` decides whether a URL can be crawled.

The policy checks, in order:

1. the URL has a hostname,
2. the host is not in `excluded_hosts`,
3. the URL does not match any exclude pattern,
4. the URL matches include patterns if any are configured,
5. the host is allowed directly or through `follow_subdomains`,
6. external assets are allowed only when `download_external_assets` is true.

If a URL is rejected, the crawler records a skip reason in the manifest.

## Fetching And Classification

`src/sitecopy/fetch.py` wraps a synchronous `httpx.Client`.

The fetcher:

- follows redirects,
- applies the configured timeout and retry count,
- sends the configured user agent,
- returns response bytes, status, content type, redirect chain, and an error
  reason for HTTP status codes `>= 400` or transport failures.

`src/sitecopy/classify.py` classifies resources from content type, URL suffix,
and a small body sample:

- HTML-like responses become `page`,
- CSS becomes `css`,
- known binary/media/script/document types and suffixed paths become `asset`,
- ambiguous HTML-looking content can still become `page`.

If an item was discovered as an asset but classifies as a page, the crawler
keeps it as an asset. This prevents asset references from unexpectedly adding
page crawl depth.

## Discovery

HTML discovery lives in `src/sitecopy/parse_html.py`.

It parses downloaded HTML with `lxml` and extracts:

- `a[href]`,
- `link[href]`,
- `script[src]`,
- `img[src]` and `img[srcset]`,
- `source[src]` and `source[srcset]`,
- `video[src]`,
- `audio[src]`,
- `iframe[src]`.

References from `a` and `iframe` are treated as page candidates. The other
HTML references are treated as assets.

CSS discovery lives in `src/sitecopy/parse_css.py`.

It parses stylesheets with `tinycss2` and extracts:

- `url(...)`,
- `@import`.

CSS references are treated as assets.

## Local Path Mapping

`src/sitecopy/map_path.py` maps canonical resources to files below the output
directory.

The top-level directory is the resource hostname:

```text
<output_dir>/<host>/...
```

Examples:

```text
https://example.com/        -> <output_dir>/example.com/index.html
https://example.com/about   -> <output_dir>/example.com/about/index.html
https://example.com/a.css   -> <output_dir>/example.com/a.css
```

Path segments are sanitized to filesystem-safe names. Pages without an HTML
extension are mapped to `index.html` under a directory matching the URL path.
Assets keep their final path segment when possible, or receive `.bin` when no
suffix exists.

When `keep_query_string_variants` is true, query parameters are encoded into
the local filename. If two canonical identities request the same local path,
the mapper appends a short hash and records a collision.

## Manifest Storage

`src/sitecopy/store.py` owns the SQLite manifest at:

```text
<output_dir>/manifest.sqlite
```

The manifest contains:

- `resources`: canonical identity, original/final URL, kind, HTTP metadata,
  checksum, local path, timestamp, and error reason.
- `referrers`: source URL, target URL, canonical target, and discovery context.
- `redirects`: redirect source identity, final identity, and redirect chain.
- `collisions`: requested and resolved local paths.
- `skips`: skipped URL, reason, and optional referrer.

The manifest is also used for resume behavior. If a resource already has a
local path and no error, the crawler skips fetching it again.

## Rewriting

After crawling completes, `Crawler._rewrite_downloaded()` rewrites references
inside downloaded HTML and CSS files.

The rewrite step builds a map from canonical URL identity to downloaded local
path. Redirect sources are also mapped to their final downloaded target when
possible.

For each HTML/CSS reference:

1. Ignore fragments and unsupported schemes such as `mailto:`, `tel:`,
   `javascript:`, and `data:`.
2. Canonicalize the reference relative to the source document.
3. Look up the canonical identity in the downloaded map.
4. If the target was downloaded, replace the reference with a local path.
5. Preserve fragments.
6. Leave references unchanged when the target was not downloaded.

The default `rewrite_mode` is `relative`, which writes links relative to the
source file. `root_relative_local` writes paths rooted at the output directory,
for example `/example.com/index.html`.

HTML rewriting uses `lxml`. CSS rewriting uses `tinycss2`.

## Validation

`src/sitecopy/validate.py` scans local output files after rewriting.

It checks HTML `href`, `src`, and `srcset` references and CSS `url(...)` /
`@import` references. Absolute HTTP(S) URLs and non-file schemes are ignored.
Relative local references are resolved against the source file; missing targets
are reported as broken local references.

The validator is used by both:

- `sitecopy validate <output_dir>`,
- the final phase of `sitecopy mirror`.

## Reporting

`src/sitecopy/report.py` writes:

```text
<output_dir>/report.json
```

The report summarizes:

- discovered pages,
- downloaded pages,
- downloaded assets,
- skipped URLs,
- resource errors,
- broken local references,
- path collisions.

It also includes the detailed broken reference list returned by validation.

## Output Layout

A typical mirror output looks like:

```text
mirror/
  manifest.sqlite
  report.json
  example.com/
    index.html
    about/
      index.html
    css/
      main.css
    img/
      logo.png
```

If multiple hosts are allowed or external assets are downloaded, each host is
written under its own top-level directory:

```text
mirror/
  example.com/
    index.html
  www.example.com/
    page/
      index.html
  cdn.example.net/
    assets/
      app.css
```

## Current Multi-Host Behavior

The crawler is not limited to a single host internally. `allowed_hosts` can
contain multiple hostnames, and `follow_subdomains` can allow subdomains of
those hostnames. `download_external_assets` can also download asset references
from hosts that are not otherwise allowed.

Path mapping already separates downloaded files by hostname, so resources from
different hosts do not share the same top-level output directory.

The main limitation is serving semantics. With the default relative rewrite
mode, links between downloaded files can point across host directories and work
when the whole output directory is served. With `root_relative_local`, rewritten
links are rooted at the output directory, not at an original production domain.
This is local mirror behavior, not virtual-host emulation.

The tool does not currently model per-domain roots, per-host configuration,
cookies, robots policy, canonical host aliases, or local virtual host routing.
It supports multi-host crawling at the URL policy and file layout level, but it
does not implement a full multidomain site-serving abstraction.

## Known Gaps

Several configuration fields and requirements exist ahead of implementation:

- `update_mode` is rejected by the CLI.
- `concurrency` is accepted but crawling is sequential.
- `respect_robots_txt` is accepted but not enforced.
- `asset_extensions_allowlist` is accepted but not enforced.
- `canonicalization_rules` are accepted but not applied.
- sitemap discovery is not implemented.
- JavaScript-driven discovery is intentionally not implemented.
