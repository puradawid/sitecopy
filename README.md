# sitecopy

`sitecopy` is a command-line website mirror for classic server-rendered sites. It starts from one URL, crawls allowed pages and page assets, writes deterministic local files, rewrites HTML/CSS references, validates the result, and produces a JSON report.

It is intended for offline browsing of mostly static multi-page websites. It does not execute JavaScript, replay logins, submit forms, solve bot protections, or clone dynamic backend behavior.

## Quick Start

Install from this repository:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Mirror a site:

```bash
sitecopy mirror https://example.com --output-dir mirror
```

Serve the mirrored files:

```bash
python -m http.server 8080 --directory mirror/example.com
```

Open:

```text
http://127.0.0.1:8080/
```

## Commands

```bash
sitecopy mirror <url> [--config config.yaml] [--output-dir mirror]
sitecopy validate <output_dir>
sitecopy report <output_dir>
```

Useful mirror flags:

```bash
sitecopy mirror https://example.com \
  --output-dir mirror \
  --max-pages 1000 \
  --max-depth 5 \
  --download-external-assets \
  --respect-robots-txt
```

## Configuration

Use `examples/config.yaml` as a starting point:

```bash
sitecopy mirror --config examples/config.yaml
```

Important defaults:

- Same host only.
- `http` and `https` are treated as one logical site.
- Subdomains are not followed unless configured.
- External assets are skipped unless configured.
- `robots.txt` is ignored unless `--respect-robots-txt` is set.
- Downloaded local references are rewritten as relative paths.

Output layout:

```text
mirror/
  manifest.sqlite
  report.json
  example.com/
    index.html
    css/
      main.css
    assets/
      logo.png
```

## Reports

Every mirror run writes `report.json`:

```json
{
  "pages_discovered": 45,
  "pages_downloaded": 44,
  "assets_downloaded": 97,
  "skipped_external": 445,
  "errors": 1,
  "broken_local_references": 1,
  "collisions": 0
}
```

Inspect it from the CLI:

```bash
sitecopy report mirror
sitecopy validate mirror
```

## Docker

Build the image:

```bash
docker build -t sitecopy .
```

Mirror a site into a host directory:

```bash
mkdir -p mirror
docker run --rm -v "$PWD/mirror:/data" sitecopy \
  mirror https://example.com --output-dir /data
```

Serve the result from the host:

```bash
python -m http.server 8080 --directory mirror/example.com
```

## Development

With `uv`:

```bash
uv sync
uv run pytest
uv run sitecopy mirror http://localhost:8000 --output-dir mirror
```

With standard Python tooling:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

## Current Limitations

- The crawler is intentionally static: no browser engine and no JavaScript-driven discovery.
- `update_mode` is recognized in configuration but not implemented in this practical v1.
- Concurrency is accepted in configuration but the current crawler runs requests sequentially for deterministic behavior.
- External links remain absolute unless external asset downloading is enabled and the target is an asset.
