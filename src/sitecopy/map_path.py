from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from .canonicalize import CanonicalURL


class PathMapper:
    def __init__(self, output_dir: Path, keep_query_variants: bool = True) -> None:
        self.output_dir = output_dir
        self.keep_query_variants = keep_query_variants
        self.claimed: dict[Path, str] = {}
        self.collisions: list[dict[str, str]] = []

    def map(self, canonical: CanonicalURL, kind: str) -> Path:
        split = urlsplit(canonical.fetch_url)
        host = split.hostname or canonical.host
        path = unquote(split.path or "/")
        relative = self._relative_path(path, split.query, kind)
        candidate = self.output_dir / _safe_segment(host) / relative
        prior = self.claimed.get(candidate)
        if prior and prior != canonical.identity:
            candidate = self._disambiguate(candidate, canonical.identity)
            self.collisions.append({"canonical_url": canonical.identity, "requested_path": str(self.output_dir / _safe_segment(host) / relative), "resolved_path": str(candidate), "reason": "path_collision"})
        self.claimed[candidate] = canonical.identity
        return candidate

    def _relative_path(self, path: str, query: str, kind: str) -> Path:
        if path in {"", "/"}:
            clean = ""
        else:
            clean = path.strip("/")
        parts = [_safe_segment(p) for p in clean.split("/") if p]
        last = parts[-1] if parts else "index"
        suffix = Path(last).suffix
        if kind == "page":
            if not parts:
                filename = "index.html"
                dirs = []
            elif suffix in {".html", ".htm", ".xhtml"}:
                filename = last
                dirs = parts[:-1]
            else:
                filename = "index.html"
                dirs = parts
        else:
            filename = last if suffix else f"{last}.bin"
            dirs = parts[:-1]
        if query and self.keep_query_variants:
            filename = _with_query_suffix(filename, query)
        return Path(*dirs, filename) if dirs else Path(filename)

    def _disambiguate(self, path: Path, identity: str) -> Path:
        digest = hashlib.sha1(identity.encode()).hexdigest()[:10]
        return path.with_name(f"{path.stem}__{digest}{path.suffix}")


def _safe_segment(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    value = value.strip("._")
    return value or "index"


def _with_query_suffix(filename: str, query: str) -> str:
    parsed = "__q_" + "_".join(f"{_safe_segment(k)}-{_safe_segment(v)}" for k, v in parse_qsl(query, keep_blank_values=True))
    path = Path(filename)
    return f"{path.stem}{parsed[:80]}{path.suffix}"
