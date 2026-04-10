from __future__ import annotations

import re
from urllib.parse import urlsplit

from .config import Config


def is_allowed_url(url: str, cfg: Config, *, is_asset: bool = False) -> tuple[bool, str | None]:
    split = urlsplit(url)
    host = (split.hostname or "").lower()
    if not host:
        return False, "missing_host"
    if host in cfg.excluded_hosts:
        return False, "excluded_host"
    if _matches_patterns(url, cfg.exclude_patterns):
        return False, "exclude_pattern"
    if cfg.include_patterns and not _matches_patterns(url, cfg.include_patterns):
        return False, "include_pattern"
    if _host_allowed(host, cfg):
        return True, None
    if is_asset and cfg.download_external_assets:
        return True, None
    return False, "external_host"


def _host_allowed(host: str, cfg: Config) -> bool:
    for allowed in cfg.allowed_hosts:
        if host == allowed:
            return True
        if cfg.follow_subdomains and host.endswith("." + allowed):
            return True
    return False


def _matches_patterns(url: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, url) for pattern in patterns)
