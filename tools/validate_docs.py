"""Validate normative-document metadata, links, and ADR/TS indexes."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

LINK_PATTERN = re.compile(r"(?<!!)\[[^]]*\]\(([^)#]+)(?:#[^)]+)?\)")
NUMBERED_PATTERN = re.compile(r"^(?:\d{4}|ts-\d{4})-.*\.md$")
REQUIRED_METADATA = ("Status",)


@dataclass(frozen=True)
class Finding:
    """A machine-readable documentation validation finding."""

    path: str
    rule: str
    message: str


def find_violations(repository_root: Path) -> list[Finding]:
    """Return broken links, missing metadata, and incomplete numbered-document indexes."""

    docs_root = repository_root / "docs"
    findings = _validate_metadata(docs_root, repository_root)
    findings.extend(_validate_links(docs_root, repository_root))
    findings.extend(_validate_index(docs_root / "adr", "README.md", repository_root))
    findings.extend(_validate_index(docs_root / "specifications", "README.md", repository_root))
    return findings


def _validate_metadata(docs_root: Path, repository_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(docs_root.rglob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        for field in REQUIRED_METADATA:
            if f"| {field} |" not in text:
                findings.append(
                    Finding(
                        path=str(path.relative_to(repository_root)),
                        rule="required-metadata",
                        message=f"Add the required '{field}' metadata field.",
                    )
                )
    return findings


def _validate_links(docs_root: Path, repository_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(docs_root.rglob("*.md")):
        for target in LINK_PATTERN.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).resolve().is_file():
                findings.append(
                    Finding(
                        path=str(path.relative_to(repository_root)),
                        rule="relative-link",
                        message=f"Fix or remove the broken relative link '{target}'.",
                    )
                )
    return findings


def _validate_index(directory: Path, index_name: str, repository_root: Path) -> list[Finding]:
    index = directory / index_name
    text = index.read_text(encoding="utf-8")
    expected = {path.name for path in directory.iterdir() if NUMBERED_PATTERN.match(path.name)}
    referenced = {target for target in LINK_PATTERN.findall(text) if NUMBERED_PATTERN.match(target)}
    findings: list[Finding] = []
    for filename in sorted(expected - referenced):
        findings.append(
            Finding(
                path=str(index.relative_to(repository_root)),
                rule="numbered-index",
                message=f"Reference '{filename}' exactly once in this index.",
            )
        )
    for filename in sorted(referenced - expected):
        findings.append(
            Finding(
                path=str(index.relative_to(repository_root)),
                rule="numbered-index",
                message=f"Remove or correct stale index reference '{filename}'.",
            )
        )
    for filename in sorted(expected & referenced):
        if text.count(f"]({filename})") != 1:
            findings.append(
                Finding(
                    path=str(index.relative_to(repository_root)),
                    rule="numbered-index",
                    message=f"Reference '{filename}' exactly once in this index.",
                )
            )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Run documentation validation and emit either concise text or JSON findings."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--format", choices=("human", "json"), default="human")
    arguments = parser.parse_args(argv)
    findings = find_violations(arguments.repository_root)
    if arguments.format == "json":
        print(json.dumps([asdict(finding) for finding in findings], sort_keys=True))
    elif findings:
        for finding in findings:
            print(f"{finding.path}: {finding.rule}: {finding.message}")
    else:
        print("Documentation validation passed.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
