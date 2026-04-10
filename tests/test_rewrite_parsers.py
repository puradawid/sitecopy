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
