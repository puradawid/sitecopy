from __future__ import annotations

import tinycss2


def discover(text: str) -> list[str]:
    urls: list[str] = []
    rules = tinycss2.parse_stylesheet(text, skip_comments=True, skip_whitespace=True)
    for rule in rules:
        if rule.type == "at-rule" and rule.lower_at_keyword == "import":
            urls.extend(_urls_from_import_tokens(rule.prelude))
        if hasattr(rule, "content") and rule.content:
            urls.extend(_urls_from_tokens(rule.content))
    return urls


def rewrite(text: str, resolver) -> str:
    rules = tinycss2.parse_stylesheet(text, skip_comments=False, skip_whitespace=False)
    for rule in rules:
        if rule.type == "at-rule" and rule.lower_at_keyword == "import":
            _rewrite_import_tokens(rule.prelude, resolver)
        if hasattr(rule, "content") and rule.content:
            _rewrite_tokens(rule.content, resolver)
    return tinycss2.serialize(rules)


def _urls_from_import_tokens(tokens) -> list[str]:
    urls: list[str] = []
    for token in tokens:
        if token.type in {"url", "string"}:
            urls.append(token.value)
            break
        if token.type == "function" and token.lower_name == "url":
            for arg in token.arguments:
                if arg.type == "string":
                    urls.append(arg.value)
                    break
            break
    return urls


def _urls_from_tokens(tokens) -> list[str]:
    urls: list[str] = []
    for token in tokens:
        if token.type == "url":
            urls.append(token.value)
        elif token.type == "function" and token.lower_name == "url":
            for arg in token.arguments:
                if arg.type == "string":
                    urls.append(arg.value)
    return urls


def _rewrite_tokens(tokens, resolver) -> None:
    for token in tokens:
        if token.type == "url":
            token.value = resolver(token.value)
            token.representation = token.value
        elif token.type == "string":
            token.value = resolver(token.value)
        elif token.type == "function" and token.lower_name == "url":
            for arg in token.arguments:
                if arg.type == "string":
                    arg.value = resolver(arg.value)


def _rewrite_import_tokens(tokens, resolver) -> None:
    for token in tokens:
        if token.type in {"url", "string"}:
            token.value = resolver(token.value)
            if token.type == "url":
                token.representation = token.value
            return
        if token.type == "function" and token.lower_name == "url":
            for arg in token.arguments:
                if arg.type == "string":
                    arg.value = resolver(arg.value)
                    return
