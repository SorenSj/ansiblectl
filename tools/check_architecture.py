"""Validate the layer-import rules in the Architecture Handbook."""

from __future__ import annotations

import argparse
import ast
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

LAYER_RULES: dict[str, set[str]] = {
    "cli": {"application", "domain", "sdk"},
    "application": {"domain"},
    "domain": set(),
    "infrastructure": {"application", "domain"},
    "plugins": {"application", "domain", "sdk"},
    "sdk": {"domain"},
}


@dataclass(frozen=True)
class Finding:
    """A machine-readable architecture violation."""

    path: str
    rule: str
    message: str


def find_violations(source_root: Path) -> list[Finding]:
    """Return every forbidden core-layer import below *source_root*."""

    findings: list[Finding] = []
    package_root = source_root / "ansiblectl"
    for path in sorted(package_root.rglob("*.py")):
        layer = _layer_for(path, package_root)
        if layer not in LAYER_RULES:
            continue
        allowed_layers = LAYER_RULES[layer]
        if layer == "cli" and path.name == "composition.py":
            # The Architecture Handbook explicitly makes this module the composition root.
            allowed_layers = allowed_layers | {"infrastructure"}
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported_layer in _imported_layers(tree):
            if imported_layer != layer and imported_layer not in allowed_layers:
                findings.append(
                    Finding(
                        path=str(path.relative_to(source_root)),
                        rule=f"{layer}-imports",
                        message=(
                            f"{layer} may not import ansiblectl.{imported_layer}; "
                            "move the dependency inward or introduce a declared port."
                        ),
                    )
                )
    return findings


def _layer_for(path: Path, package_root: Path) -> str:
    return path.relative_to(package_root).parts[0]


def _imported_layers(tree: ast.AST) -> set[str]:
    layers: set[str] = set()
    for node in ast.walk(tree):
        module = ""
        if isinstance(node, ast.Import):
            for name in node.names:
                module = name.name
                _add_layer(module, layers)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            _add_layer(node.module, layers)
    return layers


def _add_layer(module: str, layers: set[str]) -> None:
    parts = module.split(".")
    if len(parts) > 1 and parts[0] == "ansiblectl":
        layers.add(parts[1])


def main(argv: Sequence[str] | None = None) -> int:
    """Run boundary validation and emit either concise text or JSON findings."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("src"))
    parser.add_argument("--format", choices=("human", "json"), default="human")
    arguments = parser.parse_args(argv)
    findings = find_violations(arguments.source_root)
    if arguments.format == "json":
        print(json.dumps([asdict(finding) for finding in findings], sort_keys=True))
    elif findings:
        for finding in findings:
            print(f"{finding.path}: {finding.rule}: {finding.message}")
    else:
        print("Architecture boundary validation passed.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
