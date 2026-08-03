"""Unit tests for central public-boundary redaction."""

from ansiblectl.domain.redaction import REDACTED_VALUE, redact


def test_redaction_recurses_and_recognises_compound_sensitive_names() -> None:
    source = {
        "github_token": "one",
        "api-token": "two",
        "nested": [{"password": "three", "monkey": "visible"}],
        "credentials.value": "four",
        "public": ("safe", {"private_key": "five"}),
    }

    assert redact(source) == {
        "github_token": "<redacted>",
        "api-token": "<redacted>",
        "nested": [{"password": "<redacted>", "monkey": "visible"}],
        "credentials.value": "<redacted>",
        "public": ["safe", {"private_key": "<redacted>"}],
    }
    assert source["github_token"] == "one"
    assert REDACTED_VALUE == "<redacted>"


def test_redaction_preserves_scalars_and_non_sensitive_names() -> None:
    assert redact("visible") == "visible"
    assert redact({"keyboard": "visible", "tokenizer": "visible"}) == {
        "keyboard": "visible",
        "tokenizer": "visible",
    }


def test_redaction_replaces_circular_references() -> None:
    mapping: dict[str, object] = {}
    sequence: list[object] = []
    mapping["sequence"] = sequence
    sequence.append(mapping)

    assert redact(mapping) == {"sequence": ["<circular-reference>"]}


def test_redaction_bounds_excessive_nesting() -> None:
    source: list[object] = []
    current = source
    for _ in range(80):
        child: list[object] = []
        current.append(child)
        current = child

    result = redact(source)

    assert "<maximum-depth>" in repr(result)
