from __future__ import annotations

import functools
import http.server
import socketserver
import threading
from pathlib import Path

from sitecopy.cli import main


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
