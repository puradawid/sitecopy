from __future__ import annotations

import functools
import http.server
import socketserver
import threading
from pathlib import Path

import yaml

from sitecopy.cli import main
from sitecopy.config import Config
from sitecopy.crawler import Crawler
from sitecopy.fetch import FetchResult


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def serve(directory: Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = ReusableTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_mirror_downloads_and_rewrites_static_site(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        '<html><head><link rel="stylesheet" href="/css/main.css"></head>'
        '<body><a href="/about">About</a><img src="/img/logo.png"></body></html>',
        encoding="utf-8",
    )
    (site / "about").mkdir()
    (site / "about" / "index.html").write_text('<html><body><a href="/">Home</a></body></html>', encoding="utf-8")
    (site / "css").mkdir()
    (site / "css" / "main.css").write_text('body { background: url("../img/logo.png"); }', encoding="utf-8")
    (site / "img").mkdir()
    (site / "img" / "logo.png").write_bytes(b"png")

    server = serve(site)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        out = tmp_path / "mirror"
        assert main(["mirror", url, "--output-dir", str(out), "--max-pages", "10"]) == 0
    finally:
        server.shutdown()
        server.server_close()

    host_dir = next(p for p in out.iterdir() if p.is_dir())
    index = (host_dir / "index.html").read_text(encoding="utf-8")
    css = (host_dir / "css" / "main.css").read_text(encoding="utf-8")
    assert 'href="css/main.css"' in index
    assert 'href="about/index.html"' in index
    assert 'src="img/logo.png"' in index
    assert "../img/logo.png" in css
    assert (out / "report.json").exists()


def test_validate_detects_missing_local_reference(tmp_path: Path) -> None:
    out = tmp_path / "mirror"
    out.mkdir()
    (out / "index.html").write_text('<html><body><img src="missing.png"></body></html>', encoding="utf-8")
    assert main(["validate", str(out)]) == 1


def test_init_config_writes_default_template(tmp_path: Path) -> None:
    config = tmp_path / "sitecopy.yaml"

    assert main(["init-config", str(config)]) == 0

    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert data["root_url"] == ""
    assert data["allowed_hosts"] == []
    assert data["output_dir"] == "mirror"
    assert data["rewrite_mode"] == "relative"
    assert data["max_pages"] == 10000


def test_init_config_does_not_overwrite_without_force(tmp_path: Path) -> None:
    config = tmp_path / "sitecopy.yaml"
    config.write_text("root_url: existing\n", encoding="utf-8")

    assert main(["init-config", str(config)]) == 1
    assert config.read_text(encoding="utf-8") == "root_url: existing\n"
    assert main(["init-config", str(config), "--force"]) == 0
    assert yaml.safe_load(config.read_text(encoding="utf-8"))["root_url"] == ""


class FakeFetcher:
    def __init__(self, responses: dict[str, FetchResult]) -> None:
        self.responses = responses

    def fetch(self, url: str) -> FetchResult:
        return self.responses[url]

    def close(self) -> None:
        return None


def test_mirror_leaves_www_link_absolute_when_only_apex_host_is_allowed(tmp_path: Path) -> None:
    out = tmp_path / "mirror"
    cfg = Config(
        root_url="https://target.org/",
        output_dir=out,
        allowed_hosts=["target.org"],
        max_pages=10,
        resume=False,
    )
    cfg.validate()
    crawler = Crawler(cfg)
    crawler.fetcher = FakeFetcher(
        {
            "https://target.org/": FetchResult(
                url="https://target.org/",
                final_url="https://target.org/",
                status_code=200,
                content_type="text/html",
                body=b'<html><body><a href="https://www.target.org/about">About</a></body></html>',
                redirect_chain=["https://target.org/"],
            ),
        }
    )

    report = crawler.run()

    index = (out / "target.org" / "index.html").read_text(encoding="utf-8")
    assert 'href="https://www.target.org/about"' in index
    assert not (out / "www.target.org" / "about" / "index.html").exists()
    assert report["pages_downloaded"] == 1
    assert report["skipped_external"] == 1


def test_mirror_rewrites_link_between_explicitly_allowed_hosts(tmp_path: Path) -> None:
    out = tmp_path / "mirror"
    cfg = Config(
        root_url="https://www.target.org/",
        output_dir=out,
        allowed_hosts=["www.target.org", "target.org"],
        follow_subdomains=False,
        max_pages=10,
        resume=False,
    )
    cfg.validate()
    crawler = Crawler(cfg)
    crawler.fetcher = FakeFetcher(
        {
            "https://www.target.org/": FetchResult(
                url="https://www.target.org/",
                final_url="https://www.target.org/",
                status_code=200,
                content_type="text/html",
                body=b'<html><body><a href="https://target.org/about">About</a></body></html>',
                redirect_chain=["https://www.target.org/"],
            ),
            "https://target.org/about": FetchResult(
                url="https://target.org/about",
                final_url="https://target.org/about",
                status_code=200,
                content_type="text/html",
                body=b"<html><body>About</body></html>",
                redirect_chain=["https://target.org/about"],
            ),
        }
    )

    report = crawler.run()

    index = (out / "www.target.org" / "index.html").read_text(encoding="utf-8")
    assert 'href="../target.org/about/index.html"' in index
    assert (out / "target.org" / "about" / "index.html").exists()
    assert report["pages_downloaded"] == 2


def test_mirror_rewrites_links_across_allowed_hosts_with_redirects(tmp_path: Path) -> None:
    out = tmp_path / "mirror"
    cfg = Config(
        root_url="https://kali.org/",
        output_dir=out,
        allowed_hosts=["www.kali.org", "kali.org"],
        follow_subdomains=False,
        max_pages=10,
        resume=False,
    )
    cfg.validate()
    crawler = Crawler(cfg)
    crawler.fetcher = FakeFetcher(
        {
            "https://kali.org/": FetchResult(
                url="https://kali.org/",
                final_url="https://www.kali.org/",
                status_code=200,
                content_type="text/html",
                body=b'<html><body><a href="https://kali.org/docs">Docs</a></body></html>',
                redirect_chain=["https://kali.org/", "https://www.kali.org/"],
            ),
            "https://kali.org/docs": FetchResult(
                url="https://kali.org/docs",
                final_url="https://www.kali.org/docs",
                status_code=200,
                content_type="text/html",
                body=b"<html><body>Docs</body></html>",
                redirect_chain=["https://kali.org/docs", "https://www.kali.org/docs"],
            ),
        }
    )

    report = crawler.run()

    index = (out / "www.kali.org" / "index.html").read_text(encoding="utf-8")
    assert 'href="docs/index.html"' in index
    assert (out / "www.kali.org" / "docs" / "index.html").exists()
    assert report["pages_downloaded"] == 2
