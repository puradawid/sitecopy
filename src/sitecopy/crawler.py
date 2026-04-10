from __future__ import annotations

import hashlib
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import parse_css, parse_html
from .canonicalize import CanonicalURL, canonicalize
from .classify import classify
from .config import Config
from .fetch import Fetcher
from .map_path import PathMapper
from .policy import is_allowed_url
from .report import write_report
from .store import Store
from .validate import validate_output

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class QueueItem:
    canonical: CanonicalURL
    depth: int
    is_asset: bool
    referrer: str | None = None


class Crawler:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.output_dir = cfg.output_dir
        self.store = Store(self.output_dir / "manifest.sqlite")
        self.mapper = PathMapper(self.output_dir, cfg.keep_query_string_variants)
        for row in self.store.resources():
            if row["local_path"]:
                self.mapper.claimed[Path(row["local_path"])] = row["canonical_url"]
        self.fetcher = Fetcher(timeout=cfg.request_timeout_seconds, retries=cfg.retry_count, user_agent=cfg.user_agent)
        self.seen: set[str] = set()
        self.bodies: dict[str, bytes] = {}
        self.kinds: dict[str, str] = {}

    def run(self) -> dict[str, int]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        root = canonicalize(self.cfg.root_url, collapse_http_https=self.cfg.treat_http_https_as_same_host, keep_query_string_variants=self.cfg.keep_query_string_variants)
        if not root:
            raise ValueError("root_url must canonicalize to an http(s) URL")
        queue: deque[QueueItem] = deque([QueueItem(root, 0, False)])
        pages = 0
        assets = 0
        while queue:
            item = queue.popleft()
            if item.canonical.identity in self.seen:
                continue
            if self.cfg.max_depth is not None and item.depth > self.cfg.max_depth:
                self.store.add_skip(item.canonical.fetch_url, "max_depth", item.referrer)
                continue
            if item.is_asset:
                if self.cfg.max_assets is not None and assets >= self.cfg.max_assets:
                    self.store.add_skip(item.canonical.fetch_url, "max_assets", item.referrer)
                    continue
                assets += 1
            else:
                if self.cfg.max_pages is not None and pages >= self.cfg.max_pages:
                    self.store.add_skip(item.canonical.fetch_url, "max_pages", item.referrer)
                    continue
                pages += 1
            self.seen.add(item.canonical.identity)
            children = self._process(item)
            for child in children:
                if child.canonical.identity not in self.seen:
                    queue.append(child)
        self._rewrite_downloaded()
        broken = validate_output(self.output_dir)
        report = write_report(self.store, self.output_dir, broken)
        self.fetcher.close()
        self.store.close()
        return report

    def _process(self, item: QueueItem) -> list[QueueItem]:
        allowed, reason = is_allowed_url(item.canonical.fetch_url, self.cfg, is_asset=item.is_asset)
        if not allowed:
            self.store.add_skip(item.canonical.fetch_url, reason or "disallowed", item.referrer)
            return []
        if self.cfg.resume:
            existing = self.store.get_resource(item.canonical.identity)
            if existing and existing["local_path"] and not existing["error_reason"]:
                self.kinds[item.canonical.identity] = existing["kind"]
                return []
        if self.cfg.dry_run:
            self.store.upsert_resource(canonical_url=item.canonical.identity, original_url=item.canonical.original, final_url=item.canonical.fetch_url, kind="asset" if item.is_asset else "page", status_code=None, content_type=None, content_length=None, checksum=None, local_path=None, fetch_timestamp=_now(), error_reason="dry_run")
            return []
        result = self.fetcher.fetch(item.canonical.fetch_url)
        final_canon = canonicalize(result.final_url, collapse_http_https=self.cfg.treat_http_https_as_same_host, keep_query_string_variants=self.cfg.keep_query_string_variants)
        final_identity = final_canon.identity if final_canon else item.canonical.identity
        if final_identity != item.canonical.identity:
            self.store.add_redirect(item.canonical.identity, final_identity, result.redirect_chain)
        kind = classify(result.content_type, urlsplit(result.final_url).path, result.body)
        if item.is_asset and kind == "page":
            kind = "asset"
        local_path = self.mapper.map(final_canon or item.canonical, kind)
        for collision in self.mapper.collisions:
            self.store.add_collision(collision)
        self.mapper.collisions.clear()
        error = result.error
        checksum = hashlib.sha256(result.body).hexdigest() if result.body else None
        if not error:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(result.body)
            self.bodies[final_identity] = result.body
            self.kinds[final_identity] = kind
        self.store.upsert_resource(
            canonical_url=final_identity,
            original_url=item.canonical.original,
            final_url=result.final_url,
            kind=kind,
            status_code=result.status_code,
            content_type=result.content_type,
            content_length=len(result.body),
            checksum=checksum,
            local_path=str(local_path) if not error else None,
            fetch_timestamp=_now(),
            error_reason=error,
        )
        if error:
            return []
        return self._discover_children(final_canon or item.canonical, result.body, kind, item.depth)

    def _discover_children(self, source: CanonicalURL, body: bytes, kind: str, depth: int) -> list[QueueItem]:
        discovered: list[tuple[str, bool, str]] = []
        if kind == "page":
            for ref in parse_html.discover(body):
                discovered.append((ref.url, ref.tag not in {"a", "iframe"}, f"{ref.tag}[{ref.attr}]"))
        elif kind == "css":
            text = body.decode("utf-8", errors="ignore")
            for url in parse_css.discover(text):
                discovered.append((url, True, "css"))
        children: list[QueueItem] = []
        for url, is_asset, context in discovered:
            canon = canonicalize(url, base_url=source.fetch_url, collapse_http_https=self.cfg.treat_http_https_as_same_host, keep_query_string_variants=self.cfg.keep_query_string_variants)
            if not canon:
                continue
            allowed, reason = is_allowed_url(canon.fetch_url, self.cfg, is_asset=is_asset)
            self.store.add_referrer(source.identity, url, canon.identity, context)
            if not allowed:
                self.store.add_skip(canon.fetch_url, reason or "disallowed", source.identity)
                continue
            children.append(QueueItem(canon, depth + (0 if is_asset else 1), is_asset, source.identity))
        children.sort(key=lambda item: item.canonical.identity)
        return children

    def _rewrite_downloaded(self) -> None:
        local_map = self.store.downloaded_map()
        resources = self.store.resources()
        for row in resources:
            if not row["local_path"] or row["error_reason"] or row["kind"] not in {"page", "css"}:
                continue
            source_file = Path(row["local_path"])
            source_url = row["final_url"] or row["original_url"]

            def resolver(raw: str) -> str:
                if raw.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                    return raw
                fragment = ""
                if "#" in raw:
                    raw_no_fragment, fragment = raw.split("#", 1)
                    raw = raw_no_fragment
                    fragment = "#" + fragment
                canon = canonicalize(raw, base_url=source_url, collapse_http_https=self.cfg.treat_http_https_as_same_host, keep_query_string_variants=self.cfg.keep_query_string_variants)
                if not canon:
                    return raw + fragment
                target = local_map.get(canon.identity)
                if not target:
                    return raw + fragment
                if self.cfg.rewrite_mode == "root_relative_local":
                    rewritten = "/" + Path(target).relative_to(self.output_dir).as_posix()
                else:
                    rewritten = _relative(source_file, Path(target))
                return rewritten + fragment

            try:
                if row["kind"] == "page":
                    source_file.write_bytes(parse_html.rewrite(source_file.read_bytes(), resolver))
                elif row["kind"] == "css":
                    source_file.write_text(parse_css.rewrite(source_file.read_text(encoding="utf-8", errors="ignore"), resolver), encoding="utf-8")
            except Exception as exc:
                LOGGER.warning("rewrite failed for %s: %s", source_file, exc)


def _relative(source_file: Path, target_file: Path) -> str:
    import os

    return Path(os.path.relpath(target_file, source_file.parent)).as_posix()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
