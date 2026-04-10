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
