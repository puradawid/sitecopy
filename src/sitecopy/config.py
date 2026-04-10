from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


@dataclass(slots=True)
class Config:
    root_url: str
    output_dir: Path = Path("mirror")
    allowed_hosts: list[str] = field(default_factory=list)
    excluded_hosts: list[str] = field(default_factory=list)
    follow_subdomains: bool = False
    treat_http_https_as_same_host: bool = True
    max_depth: int | None = None
    max_pages: int | None = 10000
    max_assets: int | None = None
    user_agent: str = "sitecopy/0.1"
    concurrency: int = 8
    respect_robots_txt: bool = False
    request_timeout_seconds: float = 20
    retry_count: int = 2
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    asset_extensions_allowlist: list[str] = field(default_factory=list)
    download_external_assets: bool = False
    rewrite_mode: str = "relative"
    keep_query_string_variants: bool = True
    canonicalization_rules: dict[str, Any] = field(default_factory=dict)
    resume: bool = True
    update_mode: bool = False
    dry_run: bool = False
    log_level: str = "info"

    @classmethod
    def from_sources(
        cls,
        root_url: str | None,
        config_path: str | None = None,
        output_dir: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> "Config":
        data: dict[str, Any] = {}
        if config_path:
            loaded = yaml.safe_load(Path(config_path).read_text()) or {}
            if not isinstance(loaded, dict):
                raise ValueError("Config file must contain a mapping")
            data.update(loaded)
        if root_url:
            data["root_url"] = root_url
        if output_dir:
            data["output_dir"] = output_dir
        if overrides:
            data.update({k: v for k, v in overrides.items() if v is not None})
        if not data.get("root_url"):
            raise ValueError("root_url is required")
        data["output_dir"] = Path(data.get("output_dir", "mirror"))
        cfg = cls(**data)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        parsed = urlparse(self.root_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("root_url must be an absolute http(s) URL")
        if not self.allowed_hosts:
            self.allowed_hosts = [parsed.hostname or ""]
        self.allowed_hosts = [h.lower() for h in self.allowed_hosts]
        self.excluded_hosts = [h.lower() for h in self.excluded_hosts]
        if self.rewrite_mode not in {"relative", "root_relative_local"}:
            raise ValueError("rewrite_mode must be 'relative' or 'root_relative_local'")
