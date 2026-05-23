from __future__ import annotations

from dataclasses import dataclass

from lxml import html


@dataclass(slots=True)
class HtmlRef:
    url: str
    tag: str
    attr: str
    srcset: bool = False


REF_ATTRS = {
    "a": ("href",),
    "link": ("href",),
    "script": ("src",),
    "img": ("src", "srcset"),
    "source": ("src", "srcset"),
    "video": ("src",),
    "audio": ("src",),
    "iframe": ("src",),
}


def discover(body: bytes) -> list[HtmlRef]:
    doc = html.fromstring(body)
    refs: list[HtmlRef] = []
    for tag, attrs in REF_ATTRS.items():
        for el in doc.iter(tag):
            for attr in attrs:
                value = el.get(attr)
                if not value:
                    continue
                if attr == "srcset":
                    for url, _descriptor in parse_srcset(value):
                        refs.append(HtmlRef(url, tag, attr, True))
                else:
                    refs.append(HtmlRef(value, tag, attr, False))
    return refs


def rewrite(body: bytes, resolver) -> bytes:
    doc = html.fromstring(body)
    for tag, attrs in REF_ATTRS.items():
        for el in doc.iter(tag):
            for attr in attrs:
                value = el.get(attr)
                if not value:
                    continue
                if attr == "srcset":
                    rewritten = []
                    changed = False
                    for url, descriptor in parse_srcset(value):
                        new = resolver(url)
                        changed = changed or new != url
                        rewritten.append(" ".join(p for p in [new, descriptor] if p))
                    if changed:
                        el.set(attr, ", ".join(rewritten))
                else:
                    new = resolver(value)
                    if new != value:
                        el.set(attr, new)
    _ensure_utf8_charset(doc)
    return html.tostring(doc, encoding="utf-8", method="html", doctype=None)


def parse_srcset(value: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for part in value.split(","):
        tokens = part.strip().split(None, 1)
        if not tokens:
            continue
        refs.append((tokens[0], tokens[1] if len(tokens) > 1 else ""))
    return refs


def _ensure_utf8_charset(doc) -> None:
    head = doc.find(".//head")
    if head is None:
        html_el = doc if doc.tag == "html" else doc.find(".//html")
        if html_el is None:
            return
        head = html.Element("head")
        html_el.insert(0, head)
    for meta in list(head.findall("meta")):
        if meta.get("charset"):
            head.remove(meta)
            continue
        http_equiv = (meta.get("http-equiv") or "").strip().lower()
        content = (meta.get("content") or "").lower()
        if http_equiv == "content-type" and "charset=" in content:
            head.remove(meta)
    head.insert(0, html.Element("meta", charset="utf-8"))
