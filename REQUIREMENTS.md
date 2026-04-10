# Product requirements document

## 1. Purpose

Build a command-line tool that downloads a website for **local offline browsing** by:

* starting from one root URL,
* discovering all allowed linked pages,
* downloading HTML and referenced assets,
* rewriting links to local paths,
* preserving enough structure that the mirrored site can be served locally with a basic static server.

The tool is optimized for:

* classic multi-page websites,
* server-rendered pages,
* mostly static HTML/CSS/JS/image/document assets,
* limited redirect complexity,
* mixed `http`/`https` links.

The tool is **not** intended to fully clone:

* complex SPA applications,
* authenticated sessions,
* sites requiring client-side runtime APIs to render core content,
* sites with anti-bot protections,
* sites depending on dynamic backend behavior.

---

## 2. Goals

### Primary goals

The tool must:

1. Accept a root website URL and hostname allow/deny rules.
2. Crawl all reachable allowed pages from the root.
3. Follow both `http` and `https` URLs when allowed by policy.
4. Download HTML plus required CSS, JS, images, fonts, and other page assets.
5. Rewrite internal links so the mirrored site works locally through `http-server`, `python -m http.server`, or equivalent.
6. Produce deterministic output and a crawl report.
7. Be safer and more predictable than HTTrack in handling URL normalization, redirects, duplicate content, and rewriting.

### Secondary goals

The tool should:

* support resumable crawls,
* support incremental updates,
* support reasonable concurrency,
* provide dry-run and validation modes,
* be extensible with custom rewrite rules.

---

## 3. Non-goals

The first version must explicitly avoid trying to solve:

* full JavaScript execution and DOM-driven page discovery,
* form submission crawling,
* login/session replay,
* CAPTCHAs or bot defenses,
* content generated only after user interaction,
* exact browser-state replay,
* full legal or archival fidelity,
* WARC support.

This matters because existing offline-mirroring tools generally rewrite URLs and download recursive dependencies, but none of them guarantee perfect behavioral reproduction. ([httrack.com][1])

---

# 4. User stories

## Core user stories

### U1. Basic mirror

As a user, I want to run:

```bash
sitecopy mirror https://example.com
```

and get a local directory that I can serve and browse offline.

### U2. Host filtering

As a user, I want to specify:

* allowed hostnames,
* excluded hostnames,
* whether subdomains are included,

so I can mirror only the part of the site I care about.

### U3. Mixed protocol support

As a user, I want links between `http://example.com/...` and `https://example.com/...` to be treated as the same logical site when configured, so the crawler does not miss content.

### U4. Asset completeness

As a user, I want all referenced page assets to be downloaded and remapped locally so pages render correctly offline.

### U5. Repeatable output

As a user, I want the output structure and rewritten links to be deterministic across runs.

### U6. Diagnostics

As a user, I want a report showing:

* discovered URLs,
* downloaded files,
* skipped URLs,
* rewrite failures,
* broken local references after crawl.

---

# 5. Functional requirements

## 5.1 Input configuration

The tool must accept:

* `root_url` — required
* `allowed_hosts` — optional list
* `excluded_hosts` — optional list
* `follow_subdomains` — boolean
* `treat_http_https_as_same_host` — boolean
* `max_depth` — optional
* `max_pages` — optional
* `max_assets` — optional
* `output_dir` — required or defaulted
* `user_agent` — optional
* `concurrency` — optional
* `respect_robots_txt` — boolean
* `request_timeout_seconds`
* `retry_count`
* `include_patterns` — optional regex/glob
* `exclude_patterns` — optional regex/glob
* `asset_extensions_allowlist`
* `download_external_assets` — boolean
* `rewrite_mode` — `"relative"` or `"root_relative_local"`
* `keep_query_string_variants` — boolean
* `canonicalization_rules` — optional custom rules
* `resume` — boolean
* `update_mode` — boolean
* `dry_run` — boolean

### Example config

```yaml
root_url: "https://example.com"
allowed_hosts:
  - "example.com"
  - "www.example.com"
excluded_hosts:
  - "cdn.thirdparty.com"
follow_subdomains: false
treat_http_https_as_same_host: true
max_depth: null
max_pages: 10000
output_dir: "./mirror"
respect_robots_txt: true
concurrency: 8
request_timeout_seconds: 20
retry_count: 2
rewrite_mode: "relative"
download_external_assets: false
keep_query_string_variants: false
resume: true
```

---

## 5.2 URL normalization

The crawler must normalize URLs before deduplication.

Normalization rules must include:

* lowercase scheme and hostname,
* remove fragment identifiers,
* normalize default ports (`:80`, `:443`),
* normalize trailing slash policy,
* resolve relative URLs,
* decode/encode safely without changing semantics,
* optionally collapse `http` and `https` into one logical identity when configured,
* optionally strip known tracking query parameters,
* preserve query string when content may differ,
* canonicalize duplicate slash sequences where safe.

### Requirement

There must be a single internal canonical URL identity used for crawl deduplication and mapping.

### Acceptance criteria

Given:

* `https://example.com/page`
* `https://example.com/page#section`
* `https://EXAMPLE.com/page`

the crawler must treat these as one page identity.

---

## 5.3 Crawl discovery

The tool must discover followable URLs from:

* HTML anchor tags: `<a href>`
* `<link href>`
* `<script src>`
* `<img src>`
* `<source src>` and `srcset`
* `<video src>`, `<audio src>`
* `<iframe src>`
* CSS `url(...)`
* CSS `@import`
* favicon references
* common metadata references where local rendering matters

The tool should also discover:

* sitemap XML if present,
* robots.txt-discovered sitemap URLs,
* URLs from HTML forms only as references, not for submission.

The tool must not rely only on anchor tags; asset extraction is required because Wget/WebCopy-style offline browsing depends on page requisites being downloaded and links being converted. ([gnu.org][2])

---

## 5.4 Crawl policy

The crawler must:

* start from `root_url`,
* use BFS by default,
* avoid recrawling canonicalized duplicates,
* follow redirects up to configurable limit,
* record redirect chains,
* apply allow/deny filters before enqueueing,
* classify discovered URLs as:

  * HTML/page candidate
  * asset candidate
  * skipped external URL
  * skipped disallowed URL
  * error

### Protocol handling

When `treat_http_https_as_same_host=true`:

* `http://example.com/x` and `https://example.com/x` are both allowed if host is allowed,
* redirect from one to the other must not create duplicate local pages,
* a preferred protocol may be selected for naming.

---

## 5.5 Fetching

The tool must:

* use HTTP client with redirect support,
* support gzip/br compression where available,
* save response body and response metadata,
* retry transient failures,
* throttle if configured,
* support conditional re-fetch in update mode using `ETag` / `Last-Modified` when available,
* detect content type from both headers and file sniffing when necessary.

### Required metadata per fetched URL

Store in a crawl database or manifest:

* original URL
* canonical URL
* final URL after redirects
* status code
* content type
* content length
* checksum
* local output path
* referrers
* fetch timestamp
* error reason if failed

---

## 5.6 Page vs asset classification

The system must classify resources reliably:

### Page-like content

* `text/html`
* `application/xhtml+xml`

### Asset-like content

* CSS
* JS
* images
* fonts
* PDFs
* media files
* XML needed for local site navigation if referenced

### Rule

HTML pages must be parsed for more links.
Assets are downloaded but not recursively parsed unless the asset type supports references, such as CSS.

---

## 5.7 Local path mapping

The tool must map remote URLs to local filesystem paths deterministically.

### Requirements

* page URLs should map to local HTML files,
* directory-like URLs should map to `.../index.html`,
* asset files should retain meaningful extensions,
* collisions must be handled deterministically,
* query-string variants must either:

  * be preserved in filenames safely, or
  * be collapsed according to configuration.

### Examples

* `https://example.com/` → `mirror/example.com/index.html`
* `https://example.com/about` → `mirror/example.com/about/index.html`
* `https://example.com/app.css` → `mirror/example.com/app.css`
* `https://example.com/img/logo.png?v=2` → either

  * `mirror/example.com/img/logo__q_v=2.png`
  * or canonicalized to one file if configured

### Collision handling

If two distinct URLs map to same path, tool must:

* detect collision,
* apply stable disambiguation,
* record it in manifest.

---

## 5.8 Link rewriting

This is the most important module.

### HTML rewriting

For downloaded HTML files, rewrite all local-followed references so they point to the local mapped files.

Rewrite targets:

* `<a href>`
* `<img src srcset>`
* `<script src>`
* `<link href>`
* `<iframe src>`
* media tags
* preload/prefetch links if useful for local rendering

### CSS rewriting

For downloaded CSS files, rewrite:

* `url(...)`
* `@import`

### Rules

* external URLs not downloaded must remain absolute by default,
* downloaded internal URLs must be rewritten to relative local paths,
* fragment-only links must be preserved,
* mailto/tel/javascript pseudo-links must be untouched.

HTTrack and Wget both emphasize local link conversion as a core mirroring step, so this module should be treated as first-class, not post-processing glue. ([httrack.com][1])

### Acceptance criteria

Given an HTML page that references:

```html
<a href="/docs/start">Start</a>
<link rel="stylesheet" href="https://example.com/css/main.css">
<img src="../img/logo.png">
```

and those files are mirrored locally, the rewritten HTML must use correct local paths and open successfully from a local static server.

---

## 5.9 Redirect handling

The tool must:

* follow redirects during crawling,
* store final content once,
* avoid producing duplicate local pages for both pre-redirect and post-redirect URLs unless explicitly configured,
* rewrite links to the canonical final local page when safe.

### Acceptance criteria

If `/old-page` redirects to `/new-page`, internal links to `/old-page` should resolve locally to the mirrored version of `/new-page`, unless “preserve redirect identity” mode is enabled.

---

## 5.10 Validation pass

After crawling and rewriting, the tool must run a validation pass.

Checks must include:

* local rewritten HTML references resolve to existing files,
* local CSS asset URLs resolve,
* missing assets are reported,
* duplicate canonical URLs are reported,
* collisions are reported,
* pages with unresolved references are reported.

### Output

Generate a report like:

```json
{
  "pages_discovered": 1240,
  "pages_downloaded": 1197,
  "assets_downloaded": 5432,
  "skipped_external": 782,
  "errors": 16,
  "broken_local_references": 9,
  "collisions": 2
}
```

---

## 5.11 Resume and update mode

### Resume

If a crawl stops, the tool must resume using saved state.

### Update mode

The tool should:

* compare known URLs,
* re-fetch changed resources,
* preserve unchanged local files,
* re-run rewriting where dependencies changed.

---

## 5.12 Reporting and logs

The tool must generate:

* human-readable console logs,
* structured JSON log or manifest,
* final summary report.

Log levels:

* quiet
* info
* debug

Important events:

* URL enqueued
* URL skipped and why
* redirect chain
* fetch failure
* rewrite failure
* collision
* validation failure

---

# 6. Non-functional requirements

## 6.1 Performance

* Must handle at least 10,000 pages on a modest site.
* Concurrency must be configurable.
* Must avoid holding full crawl graph in memory if not necessary.
* Parsing and rewriting should stream when practical.

## 6.2 Reliability

* Single bad page must not abort whole crawl.
* Partial results must remain usable.
* Manifest/state must survive interruption.

## 6.3 Determinism

Given identical configuration and identical remote content, output paths and rewritten references must be stable.

## 6.4 Portability

* Must run on Linux and macOS at minimum.
* Windows support is desirable.
* Should be installable as a single CLI package.

## 6.5 Observability

* Structured logs
* clear error classification
* optional verbose diagnostics for URL normalization and rewrites

---

# 7. Suggested architecture

## Modules

### 7.1 CLI/config loader

Parses flags and config files.

### 7.2 Crawl frontier

Queue of URLs to visit with deduplication state.

### 7.3 URL canonicalizer

Central module for URL normalization.

### 7.4 Fetcher

HTTP client with retries, redirects, metadata capture.

### 7.5 Content classifier

Decides page vs asset vs skip.

### 7.6 Parsers

* HTML parser
* CSS parser
  Use proper parsers, not regex-only rewriting.

### 7.7 Storage mapper

Maps canonical URLs to local output paths.

### 7.8 Rewriter

Rewrites downloaded documents to local references.

### 7.9 Manifest/state store

SQLite is recommended.

### 7.10 Validator

Runs link integrity checks on output tree.

### 7.11 Reporter

Generates summary and machine-readable output.

---

# 8. Recommended implementation choices

## Language

Best options:

* **Python** for fastest iteration,
* **Go** for a more robust standalone CLI.

For Codex, Python is probably the easiest first build.

## Libraries

For Python, ask for:

* `httpx` or `requests` for fetching
* `beautifulsoup4` or `lxml` for HTML parsing
* `tinycss2` for CSS parsing
* `sqlite3` for manifest/state
* `urllib.parse` for URL normalization
* `pathlib` for path mapping

### Important instruction

Do not let Codex implement HTML/CSS rewriting with naive regex-only logic.

---

# 9. Output directory format

Recommend:

```text
mirror/
  manifest.sqlite
  report.json
  logs/
  example.com/
    index.html
    about/
      index.html
    css/
      main.css
    js/
      app.js
    images/
      logo.png
```

Optional:

* `mirror/_meta/`
* per-page metadata JSON

---

# 10. Edge cases that must be handled

Codex should explicitly implement tests for these:

1. Relative URLs like `../page`
2. Root-relative URLs like `/page`
3. Protocol-relative URLs like `//example.com/x.css`
4. Mixed `http` and `https`
5. Redirect chains
6. Trailing slash vs no trailing slash
7. Duplicate references with fragments
8. Asset URLs inside CSS
9. `srcset`
10. Query-string asset variants
11. External CDN links that are disallowed
12. Broken links returning 404
13. `index.html` mapping
14. URL-encoded filenames
15. Non-HTML content served with wrong content type
16. Canonical link tags that should not override actual crawl identity automatically
17. Pages referencing absolute production URLs that need local rewrite
18. Collision between `/about` and `/about/`

---

# 11. Acceptance test scenarios

## Scenario A: simple static site

Given a 20-page static site with local CSS/JS/images,
when mirrored,
then all pages and assets must be downloadable and locally browsable.

## Scenario B: mixed protocol

Given a site where some links point to `http://example.com/...` and others to `https://example.com/...`,
when `treat_http_https_as_same_host=true`,
then the crawler must fetch both as allowed and avoid duplicate local page creation.

## Scenario C: external asset deny

Given HTML referencing `https://cdn.example.net/app.css`,
when that hostname is excluded,
then the reference must remain absolute or be reported as skipped, but not rewritten to a broken local path.

## Scenario D: redirect normalization

Given `/old` redirects to `/new`,
then local rewritten references should resolve to one stored page.

## Scenario E: CSS assets

Given CSS containing:

```css
@import "/css/theme.css";
body { background: url("../img/bg.png"); }
```

then those referenced files must be fetched and rewritten correctly.

---

# 12. Nice-to-have features for v2

These should not block v1:

* limited headless-browser fallback for selected pages
* sitemap-first discovery mode
* robots.txt visualization
* checksum-based duplicate-content collapsing
* WARC export
* GUI
* plugin hooks for custom URL transforms

Cyotek exposes URL transforms, and HTTrack historically exposed callback/plugin-style post-processing, so extension points are a good later feature. ([docs.cyotek.com][3])

---

# 13. Explicit prompt you can give Codex

Use this as a starting instruction:

```text
Build a CLI tool in Python called `sitecopy` that mirrors classic server-rendered websites for offline browsing.

Requirements:
- Start from one root URL.
- Crawl all reachable allowed pages using BFS.
- Support allowlist and denylist for hostnames.
- Optionally treat http and https as the same logical site.
- Download HTML, CSS, JS, images, fonts, PDFs, and other referenced page assets.
- Parse HTML and CSS with real parsers, not regex-only rewriting.
- Rewrite local references in HTML and CSS so the mirrored site works from a local static server.
- Map URLs to deterministic local filesystem paths.
- Handle redirects without creating duplicate local pages unnecessarily.
- Save crawl state and metadata in SQLite.
- Support resume mode and update mode.
- Produce report.json with crawl summary, failures, skipped URLs, collisions, and broken local references.
- Include automated tests for protocol-relative URLs, redirects, CSS url() rewriting, srcset, trailing slash normalization, and path collisions.

Non-goals:
- No SPA rendering, no login/session support, no JavaScript execution for discovery in v1.

Implementation constraints:
- Use httpx, lxml or BeautifulSoup, tinycss2, sqlite3, pathlib.
- Organize the code into modules: cli, config, frontier, canonicalize, fetch, classify, parse_html, parse_css, map_path, rewrite, validate, report.
- Provide a clean CLI:
  sitecopy mirror <url> --config config.yaml
  sitecopy validate <output_dir>
  sitecopy report <output_dir>

Deliverables:
- working code
- tests
- README
- example config
```

---

# 14. My recommendation on one crucial design choice

Tell Codex this explicitly:

> Treat the project as a **URL canonicalization + rewrite engine with a crawler attached**, not as “just a crawler.”

That is the core difference between a toy downloader and something actually better than HTTrack.

If you want, I can turn this into an even more concrete **technical design doc with class/module breakdown and sample data models**.

[1]: https://www.httrack.com/html/fcguide.html?utm_source=chatgpt.com "Httrack Users Guide (3.10)"
[2]: https://www.gnu.org/software/wget/manual/wget.html?utm_source=chatgpt.com "GNU Wget 1.25.0 Manual"
[3]: https://docs.cyotek.com/cyowcopy/1.9/uritransforms.html?utm_source=chatgpt.com "Transforming URLs - Cyotek WebCopy Help"

