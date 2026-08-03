"""Safe playbook selection-validation use case."""

from dataclasses import dataclass
from pathlib import Path

from ansiblectl.domain.playbook import playbook_digest, select_playbook


@dataclass(frozen=True)
class PlaybookValidationResult:
    """Non-secret evidence produced by selection validation."""

    playbook_path: str
    revision: str
    digest: str
    findings: tuple[str, ...]
    validator: str
    validator_version: str


@dataclass(frozen=True)
class PlaybookValidationService:
    """Validate selection boundaries without invoking playbook code."""

    validator_version: str

    def validate(
        self, workspace_root: Path, identifier: Path, revision: str
    ) -> PlaybookValidationResult:
        root = workspace_root.resolve()
        selected = select_playbook(root, identifier, revision)
        return PlaybookValidationResult(
            selected.path.relative_to(root).as_posix(),
            selected.revision,
            playbook_digest(selected),
            selected.findings,
            "ansiblectl.selection",
            self.validator_version,
        )
