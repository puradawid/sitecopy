from sitecopy.canonicalize import canonicalize
from sitecopy.config import Config
from sitecopy.policy import is_allowed_url


def test_canonical_identity_strips_fragment_and_normalizes_case() -> None:
    a = canonicalize("https://example.com/page#section")
    b = canonicalize("https://EXAMPLE.com/page")
    assert a is not None
    assert b is not None
    assert a.identity == b.identity


def test_protocol_relative_and_mixed_protocol_collapse() -> None:
    a = canonicalize("//example.com/x.css", base_url="https://example.com/index.html")
    b = canonicalize("http://example.com/x.css", base_url="https://example.com/index.html")
    assert a is not None
    assert b is not None
    assert a.identity == b.identity


def test_query_variant_can_be_collapsed() -> None:
    a = canonicalize("https://example.com/logo.png?v=1", keep_query_string_variants=False)
    b = canonicalize("https://example.com/logo.png?v=2", keep_query_string_variants=False)
    assert a is not None
    assert b is not None
    assert a.identity == b.identity


def test_allowed_host_does_not_treat_www_alias_as_same_host() -> None:
    cfg = Config(root_url="https://target.org/", allowed_hosts=["target.org"])
    cfg.validate()

    allowed, reason = is_allowed_url("https://www.target.org/about", cfg)

    assert allowed is False
    assert reason == "external_host"
