"""Playbook selection-validation use-case tests."""

from pathlib import Path

from ansiblectl.application.playbook import PlaybookValidationService


def test_service_returns_relative_digest_and_validator_provenance(tmp_path: Path) -> None:
    playbook = tmp_path / "playbooks/site.yml"
    playbook.parent.mkdir()
    playbook.write_text("---\n- hosts: all\n", encoding="utf-8")

    result = PlaybookValidationService("1.2.3").validate(
        tmp_path, Path("playbooks/site.yml"), "main"
    )

    assert result.playbook_path == "playbooks/site.yml"
    assert result.revision == "main"
    assert result.digest.startswith("sha256:")
    assert result.findings == ()
    assert result.validator == "ansiblectl.selection"
    assert result.validator_version == "1.2.3"
