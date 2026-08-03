"""Playbook selection-validation use-case tests."""

from pathlib import Path

import pytest

from ansiblectl.application.playbook import PlaybookValidationService
from ansiblectl.domain.execution import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from ansiblectl.domain.playbook import PlaybookError


class RecordingSyntaxPort:
    request: ExecutionRequest | None = None

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.request = request
        return ExecutionResult(
            request.execution_id,
            ExecutionStatus.COMPLETED,
            0,
            0.1,
            "/private/stdout.log",
        )


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
    assert result.syntax_check is None


def test_explicit_syntax_check_uses_safe_ansible_argument_vector(tmp_path: Path) -> None:
    playbook = tmp_path / "site.yml"
    playbook.write_text("---\n- hosts: all\n", encoding="utf-8")
    port = RecordingSyntaxPort()

    result = PlaybookValidationService("1.2.3", port).validate(
        tmp_path,
        Path("site.yml"),
        "main",
        syntax_check=True,
        environment={"PATH": "/bin"},
        timeout_seconds=10,
    )

    assert port.request is not None
    assert port.request.argv == ("ansible-playbook", "--syntax-check", str(playbook))
    assert port.request.environment == {"PATH": "/bin"}
    assert port.request.timeout_seconds == 10
    assert port.request.operation == "playbook.syntax_check"
    assert result.syntax_check is not None
    assert result.syntax_check.status is ExecutionStatus.COMPLETED
    assert result.syntax_check.validator == "ansible-playbook --syntax-check"
    assert result.syntax_check.stdout_reference == "/private/stdout.log"


def test_syntax_check_requires_configured_port(tmp_path: Path) -> None:
    playbook = tmp_path / "site.yml"
    playbook.write_text("---\n", encoding="utf-8")

    with pytest.raises(PlaybookError, match="not configured"):
        PlaybookValidationService("1.2.3").validate(
            tmp_path, Path("site.yml"), "main", syntax_check=True
        )
