from __future__ import annotations

import json
from pathlib import Path

from .store import Store


def write_report(store: Store, output_dir: Path, broken_refs: list[dict[str, str]]) -> dict[str, int]:
    rows = store.resources()
    report = {
        "pages_discovered": sum(1 for r in rows if r["kind"] == "page"),
        "pages_downloaded": sum(1 for r in rows if r["kind"] == "page" and r["local_path"] and not r["error_reason"]),
        "assets_downloaded": sum(1 for r in rows if r["kind"] in {"asset", "css"} and r["local_path"] and not r["error_reason"]),
        "skipped_external": store.count("skips"),
        "errors": sum(1 for r in rows if r["error_reason"]),
        "broken_local_references": len(broken_refs),
        "collisions": store.count("collisions"),
    }
    (output_dir / "report.json").write_text(json.dumps({**report, "broken_references": broken_refs}, indent=2), encoding="utf-8")
    return report
