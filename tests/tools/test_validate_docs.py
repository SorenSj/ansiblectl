"""Normative-document validator tests."""

from pathlib import Path

from tools.validate_docs import find_violations


def test_repository_documentation_is_valid() -> None:
    assert find_violations(Path(".")) == []


def test_broken_relative_link_has_actionable_finding(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    adr = docs / "adr"
    specifications = docs / "specifications"
    adr.mkdir(parents=True)
    specifications.mkdir()
    (docs / "example.md").write_text(
        "| Status | Normative |\n[broken](missing.md)\n", encoding="utf-8"
    )
    (adr / "README.md").write_text("", encoding="utf-8")
    (specifications / "README.md").write_text("", encoding="utf-8")

    findings = find_violations(tmp_path)

    assert [(finding.rule, finding.message) for finding in findings] == [
        ("relative-link", "Fix or remove the broken relative link 'missing.md'.")
    ]


def test_orphaned_numbered_specification_has_an_actionable_index_finding(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    adr, specifications = docs / "adr", docs / "specifications"
    adr.mkdir(parents=True)
    specifications.mkdir()
    (adr / "README.md").write_text("", encoding="utf-8")
    (specifications / "README.md").write_text("", encoding="utf-8")
    (specifications / "ts-9999-orphan.md").write_text("| Status | Normative |\n", encoding="utf-8")

    findings = find_violations(tmp_path)

    assert [(finding.rule, finding.message) for finding in findings] == [
        ("numbered-index", "Reference 'ts-9999-orphan.md' exactly once in this index.")
    ]
