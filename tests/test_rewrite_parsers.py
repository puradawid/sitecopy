from sitecopy import parse_css, parse_html


def test_html_rewrites_srcset_and_regular_refs() -> None:
    body = b'<html><body><a href="/docs/start">Start</a><img srcset="/a.png 1x, /b.png 2x"></body></html>'
    rewritten = parse_html.rewrite(body, lambda url: {"/docs/start": "docs/start/index.html", "/a.png": "a.png", "/b.png": "b.png"}.get(url, url))
    text = rewritten.decode()
    assert 'href="docs/start/index.html"' in text
    assert 'srcset="a.png 1x, b.png 2x"' in text


def test_css_discovers_and_rewrites_import_and_url() -> None:
    css = '@import "/css/theme.css"; body { background: url("../img/bg.png"); }'
    assert parse_css.discover(css) == ["/css/theme.css", "../img/bg.png"]
    rewritten = parse_css.rewrite(css, lambda url: {"../img/bg.png": "img/bg.png", "/css/theme.css": "css/theme.css"}.get(url, url))
    assert "css/theme.css" in rewritten
    assert "img/bg.png" in rewritten


def test_html_rewrite_updates_legacy_charset_declaration_to_utf8() -> None:
    body = '<html><head><meta charset="windows-1251"></head><body><a href="/docs/start">Привет</a></body></html>'.encode("cp1251")
    rewritten = parse_html.rewrite(body, lambda url: "docs/start/index.html" if url == "/docs/start" else url)
    text = rewritten.decode("utf-8")

    assert "Привет" in text
    assert 'href="docs/start/index.html"' in text
    assert 'meta charset="utf-8"' in text
    assert 'meta charset="windows-1251"' not in text


def test_html_rewrite_replaces_http_equiv_content_type_meta_with_utf8_charset() -> None:
    body = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1255"></head><body><a href="/docs/start">שלום</a></body></html>'.encode("cp1255")
    rewritten = parse_html.rewrite(body, lambda url: "docs/start/index.html" if url == "/docs/start" else url)
    text = rewritten.decode("utf-8")

    assert "שלום" in text
    assert 'href="docs/start/index.html"' in text
    assert 'meta charset="utf-8"' in text
    assert "http-equiv" not in text
