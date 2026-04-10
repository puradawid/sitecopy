from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .crawler import Crawler
from .validate import validate_output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sitecopy")
    sub = parser.add_subparsers(dest="command", required=True)

    mirror = sub.add_parser("mirror", help="Mirror a website")
    mirror.add_argument("url", nargs="?")
    mirror.add_argument("--config")
    mirror.add_argument("--output-dir")
    mirror.add_argument("--max-depth", type=int)
    mirror.add_argument("--max-pages", type=int)
    mirror.add_argument("--concurrency", type=int)
    mirror.add_argument("--respect-robots-txt", action="store_true")
    mirror.add_argument("--download-external-assets", action="store_true")
    mirror.add_argument("--dry-run", action="store_true")
    mirror.add_argument("--log-level", choices=["quiet", "info", "debug"], default=None)

    validate = sub.add_parser("validate", help="Validate a mirrored output directory")
    validate.add_argument("output_dir")

    report = sub.add_parser("report", help="Print report.json")
    report.add_argument("output_dir")

    init_config = sub.add_parser("init-config", help="Create a default config file")
    init_config.add_argument("path", nargs="?", default="config.yaml")
    init_config.add_argument("--force", action="store_true", help="Overwrite an existing config file")

    args = parser.parse_args(argv)
    if args.command == "mirror":
        overrides = {
            "max_depth": args.max_depth,
            "max_pages": args.max_pages,
            "concurrency": args.concurrency,
            "respect_robots_txt": True if args.respect_robots_txt else None,
            "download_external_assets": True if args.download_external_assets else None,
            "dry_run": True if args.dry_run else None,
            "log_level": args.log_level,
        }
        cfg = Config.from_sources(args.url, args.config, args.output_dir, overrides)
        _setup_logging(cfg.log_level)
        if cfg.update_mode:
            raise SystemExit("update_mode is not implemented in practical v1")
        result = Crawler(cfg).run()
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "validate":
        broken = validate_output(Path(args.output_dir))
        print(json.dumps({"broken_local_references": len(broken), "broken_references": broken}, indent=2))
        return 1 if broken else 0
    if args.command == "report":
        path = Path(args.output_dir) / "report.json"
        if not path.exists():
            print(f"report not found: {path}", file=sys.stderr)
            return 1
        print(path.read_text(encoding="utf-8"))
        return 0
    if args.command == "init-config":
        path = Path(args.path)
        if path.exists() and not args.force:
            print(f"config already exists: {path} (use --force to overwrite)", file=sys.stderr)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(_default_config_template(), sort_keys=False), encoding="utf-8")
        print(f"created config: {path}")
        return 0
    return 1


def _default_config_template() -> dict[str, Any]:
    template: dict[str, Any] = {}
    for item in fields(Config):
        if item.name == "root_url":
            template[item.name] = ""
        elif item.default is not MISSING:
            template[item.name] = _config_value(item.default)
        elif item.default_factory is not MISSING:
            template[item.name] = _config_value(item.default_factory())
    return template


def _config_value(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _setup_logging(level: str) -> None:
    if level == "quiet":
        logging.basicConfig(level=logging.ERROR)
    elif level == "debug":
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    raise SystemExit(main())
