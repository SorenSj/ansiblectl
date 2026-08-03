"""Architecture-boundary validator tests."""

from pathlib import Path

from tools.check_architecture import find_violations


def test_repository_source_obeys_layer_rules() -> None:
    assert find_violations(Path("src")) == []


def test_forbidden_layer_import_has_actionable_finding(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    domain = source_root / "ansiblectl" / "domain"
    domain.mkdir(parents=True)
    (domain / "invalid.py").write_text("import ansiblectl.cli.main\n", encoding="utf-8")

    findings = find_violations(source_root)

    assert len(findings) == 1
    assert findings[0].rule == "domain-imports"
    assert "move the dependency inward" in findings[0].message
