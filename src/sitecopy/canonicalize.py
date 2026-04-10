from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


@dataclass(frozen=True, slots=True)
class CanonicalURL:
    original: str
    fetch_url: str
    identity: str
    scheme: str
    host: str
    path: str
    query: str


def canonicalize(
    url: str,
    *,
    base_url: str | None = None,
    collapse_http_https: bool = True,
    keep_query_string_variants: bool = True,
    strip_tracking_params: bool = False,
) -> CanonicalURL | None:
    joined = urljoin(base_url, url) if base_url else url
    split = urlsplit(joined)
    if split.scheme.lower() not in {"http", "https"}:
        return None
    host = (split.hostname or "").lower()
    if not host:
        return None
    scheme = split.scheme.lower()
    port = split.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = _normalize_path(split.path or "/")
    query = _normalize_query(split.query, keep_query_string_variants, strip_tracking_params)
    fetch_url = urlunsplit((scheme, netloc, path, query, ""))
    identity_scheme = "site" if collapse_http_https else scheme
    identity = urlunsplit((identity_scheme, netloc, path, query, ""))
    return CanonicalURL(original=url, fetch_url=fetch_url, identity=identity, scheme=scheme, host=host, path=path, query=query)


def _normalize_path(path: str) -> str:
    decoded = unquote(path)
    parts: list[str] = []
    for part in decoded.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    normalized = "/" + "/".join(parts)
    if path.endswith("/") and not normalized.endswith("/"):
        normalized += "/"
    return quote(normalized, safe="/:@")


def _normalize_query(query: str, keep_variants: bool, strip_tracking: bool) -> str:
    if not keep_variants:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    if strip_tracking:
        pairs = [(k, v) for k, v in pairs if k.lower() not in TRACKING_PARAMS]
    return urlencode(pairs, doseq=True)
