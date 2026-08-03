"""Safe playbook selection and optional syntax-validation use case."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.domain.execution import ExecutionPort, ExecutionRequest, ExecutionStatus
from ansiblectl.domain.playbook import PlaybookError, playbook_digest, select_playbook


@dataclass(frozen=True)
class SyntaxCheckEvidence:
    """Safe result and provenance for one explicit Ansible syntax check."""

    status: ExecutionStatus
    exit_code: int | None
    validator: str
    stdout_reference: str | None
    stderr_reference: str | None
    diagnostic: str | None


@dataclass(frozen=True)
class PlaybookValidationResult:
    """Non-secret evidence produced by selection validation."""

    playbook_path: str
    revision: str
    digest: str
    findings: tuple[str, ...]
    validator: str
    validator_version: str
    syntax_check: SyntaxCheckEvidence | None = None


@dataclass(frozen=True)
class PlaybookValidationService:
    """Validate selection boundaries without invoking playbook code."""

    validator_version: str
    syntax_port: ExecutionPort | None = None

    def validate(
        self,
        workspace_root: Path,
        identifier: Path,
        revision: str,
        *,
        syntax_check: bool = False,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 300.0,
    ) -> PlaybookValidationResult:
        root = workspace_root.resolve()
        selected = select_playbook(root, identifier, revision)
        syntax_evidence = None
        if syntax_check:
            if self.syntax_port is None:
                raise PlaybookError("Ansible syntax validation is not configured.")
            execution = self.syntax_port.execute(
                ExecutionRequest.for_playbook(
                    ("ansible-playbook", "--syntax-check", str(selected.path)),
                    root,
                    environment or {},
                    selected,
                    timeout_seconds,
                    operation="playbook.syntax_check",
                )
            )
            syntax_evidence = SyntaxCheckEvidence(
                execution.status,
                execution.exit_code,
                "ansible-playbook --syntax-check",
                execution.stdout_reference,
                execution.stderr_reference,
                execution.diagnostic,
            )
        return PlaybookValidationResult(
            selected.path.relative_to(root).as_posix(),
            selected.revision,
            playbook_digest(selected),
            selected.findings,
            "ansiblectl.selection",
            self.validator_version,
            syntax_evidence,
        )
