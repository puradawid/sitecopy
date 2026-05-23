from pathlib import Path

from sitecopy.canonicalize import canonicalize
from sitecopy.map_path import PathMapper


def test_index_and_extensionless_page_mapping(tmp_path: Path) -> None:
    mapper = PathMapper(tmp_path)
    root = canonicalize("https://example.com/")
    about = canonicalize("https://example.com/about")
    assert root is not None
    assert about is not None
    assert mapper.map(root, "page") == tmp_path / "example.com" / "index.html"
    assert mapper.map(about, "page") == tmp_path / "example.com" / "about" / "index.html"


def test_collision_is_disambiguated(tmp_path: Path) -> None:
    mapper = PathMapper(tmp_path)
    a = canonicalize("https://example.com/about")
    b = canonicalize("https://example.com/about/")
    assert a is not None
    assert b is not None
    first = mapper.map(a, "page")
    second = mapper.map(b, "page")
    assert first != second
    assert mapper.collisions


def test_non_latin_page_segments_collapse_to_index_and_collide(tmp_path: Path) -> None:
    mapper = PathMapper(tmp_path)
    russian = canonicalize("https://ru.wikipedia.org/wiki/Россия")
    hebrew = canonicalize("https://ru.wikipedia.org/wiki/Украина")
    assert russian is not None
    assert hebrew is not None

    first = mapper.map(russian, "page")
    second = mapper.map(hebrew, "page")

    assert first == tmp_path / "ru.wikipedia.org" / "wiki" / "index" / "index.html"
    assert second.name.startswith("index__")
    assert mapper.collisions


def test_idn_host_collapses_to_index_directory(tmp_path: Path) -> None:
    mapper = PathMapper(tmp_path)
    page = canonicalize("https://пример.рф/путь")
    assert page is not None

    assert mapper.map(page, "page") == tmp_path / "index" / "index" / "index.html"
