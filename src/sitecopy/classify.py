from __future__ import annotations

from pathlib import Path

PAGE_TYPES = {"text/html", "application/xhtml+xml"}
CSS_TYPES = {"text/css"}
ASSET_TYPES = (
    "text/css",
    "application/javascript",
    "text/javascript",
    "image/",
    "font/",
    "application/font",
    "application/pdf",
    "audio/",
    "video/",
    "application/xml",
    "text/xml",
)
PAGE_EXTENSIONS = {"", ".html", ".htm", ".xhtml"}
CSS_EXTENSIONS = {".css"}


def classify(content_type: str | None, url_path: str, body: bytes = b"") -> str:
    media = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = Path(url_path).suffix.lower()
    sample = body[:512].lstrip().lower()
    if media in PAGE_TYPES or (not media and suffix in PAGE_EXTENSIONS and sample.startswith((b"<!doctype html", b"<html"))):
        return "page"
    if media in CSS_TYPES or suffix in CSS_EXTENSIONS:
        return "css"
    if media.startswith(ASSET_TYPES) or suffix:
        return "asset"
    if sample.startswith((b"<!doctype html", b"<html")):
        return "page"
    return "asset"
