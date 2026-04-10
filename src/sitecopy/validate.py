from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import html

from . import parse_css


def validate_output(output_dir: Path) -> list[dict[str, str]]:
    broken: list[dict[str, str]] = []
    for file in output_dir.rglob("*"):
        if not file.is_file() or file.name in {"manifest.sqlite", "report.json"}:
            continue
        if file.suffix.lower() in {".html", ".htm", ".xhtml"}:
            try:
                doc = html.fromstring(file.read_bytes())
            except Exception as exc:
                broken.append({"source": str(file), "target": "", "reason": f"parse_error:{exc.__class__.__name__}"})
                continue
            for attr in ("href", "src"):
                for el in doc.xpath(f"//*[@{attr}]"):
                    _check_ref(file, el.get(attr), broken)
            for el in doc.xpath("//*[@srcset]"):
                for part in el.get("srcset").split(","):
                    _check_ref(file, part.strip().split(None, 1)[0], broken)
        elif file.suffix.lower() == ".css":
            try:
                for ref in parse_css.discover(file.read_text(encoding="utf-8", errors="ignore")):
                    _check_ref(file, ref, broken)
            except Exception as exc:
                broken.append({"source": str(file), "target": "", "reason": f"parse_error:{exc.__class__.__name__}"})
    return broken


def _check_ref(source: Path, ref: str | None, broken: list[dict[str, str]]) -> None:
    if not ref or ref.startswith(("#", "http://", "https://", "mailto:", "tel:", "javascript:", "data:")):
        return
    parsed = urlsplit(ref)
    if parsed.scheme or parsed.netloc:
        return
    target = (source.parent / unquote(parsed.path)).resolve()
    if not target.exists():
        broken.append({"source": str(source), "target": ref, "reason": "missing_local_file"})
